use gb_bootstrap::candidate_recipe::build_eh_recipe_package;

fn main() {
    let mut arguments = std::env::args().skip(1);
    let version: u16 = arguments.next().unwrap().parse().unwrap();
    let path = arguments.next().unwrap();
    assert!(arguments.next().is_none());
    std::fs::write(path, build_eh_recipe_package(version).unwrap()).unwrap();
}
