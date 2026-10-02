//! Additional profile-8 programs built from the bounded logical teaching owner.
//! Only existing VM operations are used. Every carried example is evaluated
//! through the compact package's normal admission path before bytes are returned.

use std::collections::BTreeMap;

use toml::Value;

use crate::body_recipe_v1::revision_recipe_builders;
use crate::candidate_recipe::{
    EncodedTable, RecipeBuilder, Shape, encode_package_with_tables, finalize, r3_eh_tables,
};
use crate::recipe_wire_v2::{encode_recipe_package_v2, evaluate_serialized_recipe_v2};
use crate::recovery_recipe_v2::recovery_builders_and_tables;
use crate::{BootstrapError, RejectCode, Result};

const SOURCE: &[u8] = include_bytes!("../../../spec/recipe-teaching-v2.toml");
const SOURCE_MAX: usize = 65_536;

pub(crate) struct Example {
    pub(crate) recipe: u16,
    pub(crate) input: Vec<u8>,
    pub(crate) output: Vec<u8>,
}

struct Source {
    tables: Vec<EncodedTable>,
    builders: Vec<RecipeBuilder>,
    examples: Vec<Example>,
}

fn invalid() -> BootstrapError {
    BootstrapError {
        code: RejectCode::Recipe,
        offset: None,
    }
}

pub(crate) fn exact_table<'a>(value: &'a Value, keys: &[&str]) -> Result<&'a toml::Table> {
    let table = value.as_table().ok_or_else(invalid)?;
    if table.len() != keys.len() || keys.iter().any(|key| !table.contains_key(*key)) {
        return Err(invalid());
    }
    Ok(table)
}

pub(crate) fn number(value: &Value) -> Result<u64> {
    value
        .as_integer()
        .and_then(|value| u64::try_from(value).ok())
        .ok_or_else(invalid)
}

pub(crate) fn bounded_array(value: &Value, minimum: usize, maximum: usize) -> Result<&[Value]> {
    let values = value.as_array().ok_or_else(invalid)?;
    if !(minimum..=maximum).contains(&values.len()) {
        return Err(invalid());
    }
    Ok(values)
}

pub(crate) fn shape(kind: u64, width: u64, allow_table: bool) -> Result<Shape> {
    let valid = match kind {
        0 => (1..=64).contains(&width),
        1 => width == 1,
        2 | 3 => (1..=1_048_576).contains(&width),
        4 => allow_table && (1..=1_048_576).contains(&width),
        5 => width == 16,
        _ => false,
    };
    if !valid {
        return Err(invalid());
    }
    Ok(Shape {
        kind: kind as u8,
        width: width as u32,
    })
}

pub(crate) fn descriptors(value: &Value, minimum: usize) -> Result<Vec<Shape>> {
    bounded_array(value, minimum, 64)?
        .iter()
        .map(|value| {
            let pair = bounded_array(value, 2, 2)?;
            shape(number(&pair[0])?, number(&pair[1])?, false)
        })
        .collect()
}

pub(crate) fn hex(value: &Value) -> Result<Vec<u8>> {
    let text = value.as_str().ok_or_else(invalid)?;
    if text.len() % 2 != 0 || text.len() > SOURCE_MAX {
        return Err(invalid());
    }
    let digit = |byte| match byte {
        b'0'..=b'9' => Ok(byte - b'0'),
        b'a'..=b'f' => Ok(byte - b'a' + 10),
        _ => Err(invalid()),
    };
    text.as_bytes()
        .chunks_exact(2)
        .map(|pair| Ok(digit(pair[0])? * 16 + digit(pair[1])?))
        .collect()
}

pub(crate) fn arity(opcode: u64) -> Result<usize> {
    match opcode {
        1 | 2 | 24 | 25 => Ok(0),
        5 | 14 | 22 => Ok(1),
        3 | 20 | 23 => Ok(3),
        4 | 6..=13 | 15..=19 | 21 => Ok(2),
        _ => Err(invalid()),
    }
}

fn parse(source: &[u8]) -> Result<Source> {
    if source.len() > SOURCE_MAX {
        return Err(invalid());
    }
    let text = std::str::from_utf8(source).map_err(|_| invalid())?;
    let value: Value = toml::from_str(text).map_err(|_| invalid())?;
    let root = exact_table(&value, &["version", "tables", "recipes", "examples"])?;
    if number(&root["version"])? != 1 {
        return Err(invalid());
    }
    let mut tables = Vec::new();
    for (row, (expected, expected_payload)) in bounded_array(&root["tables"], 1, 1)?
        .iter()
        .zip([([21, 0, 8, 3], vec![7, 8, 9])])
    {
        let table = exact_table(row, &["id", "type", "width", "count", "payload"])?;
        let values = [
            number(&table["id"])?,
            number(&table["type"])?,
            number(&table["width"])?,
            number(&table["count"])?,
        ];
        let payload = hex(&table["payload"])?;
        if values != expected || payload != expected_payload {
            return Err(invalid());
        }
        tables.push((
            values[0] as u16,
            values[1] as u8,
            values[2] as u32,
            values[3] as u32,
            payload,
        ));
    }
    let mut builders = Vec::new();
    let mut steps = BTreeMap::<u16, u64>::new();
    let mut interfaces = BTreeMap::from([(105, vec![Shape::uint(32)])]);
    for (index, value) in bounded_array(&root["recipes"], 5, 5)?.iter().enumerate() {
        let row = exact_table(value, &["id", "inputs", "outputs", "nodes"])?;
        let id = number(&row["id"])?;
        if id != [210, 211, 212, 213, 214][index] {
            return Err(invalid());
        }
        let id = id as u16;
        let inputs = descriptors(&row["inputs"], 0)?;
        let outputs = descriptors(&row["outputs"], 1)?;
        let input_count = inputs.len();
        interfaces.insert(id, inputs.clone());
        let mut builder = RecipeBuilder::custom(id, inputs, outputs);
        let mut recipe_steps = 0u64;
        for (node_index, value) in bounded_array(&row["nodes"], 1, 256)?.iter().enumerate() {
            let values = bounded_array(value, 9, 9)?;
            let numbers: Vec<_> = values.iter().map(number).collect::<Result<_>>()?;
            let opcode = numbers[0];
            let output = shape(numbers[1], numbers[2], true)?;
            let count = arity(opcode)?;
            if numbers[3] != count as u64 || numbers[4 + count..7].iter().any(|value| *value != 0) {
                return Err(invalid());
            }
            let mut arguments = Vec::new();
            for argument in &numbers[4..4 + count] {
                if *argument == 0 || *argument > (input_count + node_index) as u64 {
                    return Err(invalid());
                }
                arguments.push(*argument as u16);
            }
            let auxiliary = u16::try_from(numbers[7]).map_err(|_| invalid())?;
            let immediate = numbers[8];
            if (!matches!(opcode, 2 | 5 | 22) && auxiliary != 0)
                || (!matches!(opcode, 1 | 5 | 14 | 22 | 25) && immediate != 0)
            {
                return Err(invalid());
            }
            let node_steps = if opcode == 22 {
                if immediate > 1_048_576 {
                    return Err(invalid());
                }
                // Teaching iteration targets are earlier teaching rows. Check
                // references and arithmetic before the shared trusted builder.
                let body_steps = steps.get(&auxiliary).ok_or_else(invalid)?;
                immediate
                    .checked_mul(*body_steps)
                    .and_then(|value| value.checked_add(1))
                    .ok_or_else(invalid)?
            } else {
                1
            };
            recipe_steps = recipe_steps.checked_add(node_steps).ok_or_else(invalid)?;
            if recipe_steps > 268_435_456 {
                return Err(invalid());
            }
            builder.push(opcode as u8, output, &arguments, auxiliary, immediate);
        }
        steps.insert(id, recipe_steps);
        builders.push(builder);
    }
    let mut examples = Vec::new();
    let expected_recipes = [211, 211, 105, 211, 211, 212, 214, 214];
    for (index, value) in bounded_array(&root["examples"], 8, 8)?.iter().enumerate() {
        let row = exact_table(value, &["label", "recipe", "inputs", "output"])?;
        let label = if index == 0 {
            "worked"
        } else if index == 1 {
            "held"
        } else {
            "additional"
        };
        if row["label"].as_str() != Some(label)
            || number(&row["recipe"])? != expected_recipes[index]
        {
            return Err(invalid());
        }
        let recipe = expected_recipes[index] as u16;
        let interface = &interfaces[&recipe];
        let values = bounded_array(&row["inputs"], interface.len(), interface.len())?;
        let mut input = Vec::new();
        for (value, shape) in values.iter().zip(interface) {
            let encoded = hex(value)?;
            let length = if shape.kind == 3 {
                shape.width
            } else {
                shape.width.div_ceil(8)
            };
            if encoded.len() != length as usize {
                return Err(invalid());
            }
            input.extend(encoded);
        }
        let output = hex(&row["output"])?;
        if output.len() < 2 {
            return Err(invalid());
        }
        examples.push(Example {
            recipe,
            input,
            output,
        });
    }
    Ok(Source {
        tables,
        builders,
        examples,
    })
}

/// Parse bounded logical source, derive complete resources, admit the compact
/// profile-8 package and verify every example before returning any package.
pub fn build_teaching_recipe_package_from_source(source: &[u8]) -> Result<Vec<u8>> {
    let source = parse(source)?;
    let mut tables = r3_eh_tables();
    if !tables
        .iter()
        .any(|row| row == &(5, 0, 8, 256, (0..=255u8).collect()))
    {
        return Err(invalid());
    }
    tables.extend(source.tables);
    let (recovery_builders, recovery_tables) = recovery_builders_and_tables()?;
    tables.extend(recovery_tables);
    tables.sort_by_key(|row| row.0);
    let mut recipes = Vec::new();
    let mut builders: Vec<_> = revision_recipe_builders()
        .into_iter()
        .filter(|builder| ![106, 110, 111].contains(&builder.id))
        .chain(recovery_builders)
        .chain(source.builders)
        .collect();
    builders.sort_by_key(|builder| builder.id);
    for builder in builders {
        recipes.push(finalize(builder, &recipes));
    }
    let expanded = encode_package_with_tables(8, &recipes, tables);
    let compact = encode_recipe_package_v2(&expanded, 8)?;
    for example in source.examples {
        if evaluate_serialized_recipe_v2(&compact, 8, example.recipe, &example.input)?
            != example.output
        {
            return Err(invalid());
        }
    }
    Ok(compact)
}

/// Independently generate the carried teaching package from its logical owner.
pub fn build_teaching_recipe_package() -> Result<Vec<u8>> {
    build_teaching_recipe_package_from_source(SOURCE)
}

pub(crate) fn teaching_examples() -> Result<Vec<Example>> {
    Ok(parse(SOURCE)?.examples)
}
