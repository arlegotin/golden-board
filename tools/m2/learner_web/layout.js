(function (global) {
    "use strict";

    // Display pixels only. These bounds apply to any content-v0 matrix and
    // carry no assumptions about the meaning of its rows, columns or atoms.
    function matrixLayout({rows,columns,availableWidth,zoom=1,digits=1}) {
        if(!Number.isInteger(rows) || !Number.isInteger(columns) || rows<1 || columns<1 ||
            rows*columns>65535 || !Number.isFinite(availableWidth) || availableWidth<=0 ||
            !Number.isFinite(zoom) || zoom<0.5 || zoom>3 ||
            !Number.isInteger(digits) || digits<1 || digits>10) throw new Error("invalid_layout");
        const minimum=Math.max(24,digits*8+8);
        const fitted=Math.max(minimum,Math.min(96,Math.floor((availableWidth-4)/columns)));
        const cellPixels=Math.max(minimum,Math.min(96,Math.round(fitted*zoom)));
        const width=columns*cellPixels+4,height=rows*cellPixels+4;
        return {cellPixels,width,height,overflowX:width>availableWidth};
    }

    const api=Object.freeze({matrixLayout});
    global.GBLearnerLayout=api;
    if(typeof module==="object" && module.exports) module.exports=api;
})(globalThis);
