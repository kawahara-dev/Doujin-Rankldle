(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RankIdleBookmarklet = api;
})(typeof globalThis !== "undefined" ? globalThis : this, () => {
  function stripComments(source) {
    let output = "";
    let quote = "";
    let escaped = false;

    for (let index = 0; index < source.length; index += 1) {
      const char = source[index];
      const next = source[index + 1];

      if (quote) {
        output += char;
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === quote) quote = "";
        continue;
      }
      if (char === '"' || char === "'" || char === "`") {
        quote = char;
        output += char;
      } else if (char === "/" && next === "/") {
        while (index + 1 < source.length && source[index + 1] !== "\n") index += 1;
      } else if (char === "/" && next === "*") {
        index += 2;
        while (index < source.length && !(source[index] === "*" && source[index + 1] === "/")) index += 1;
        index += 1;
        output += " ";
      } else {
        output += char;
      }
    }
    return output;
  }

  function minify(source) {
    const code = stripComments(String(source).replace(/^\uFEFF/, ""))
      .split(/\r?\n/)
      .map(line => line.trim())
      .filter(Boolean)
      .join(" ")
      .replace(/^\(\(\)\s*=>\s*\{/, "(()=>{");
    const bookmarklet = `javascript:${code}`;
    if (!bookmarklet.startsWith("javascript:(()=>{")) {
      throw new Error("bookmarklet.js must start with (()=>{");
    }
    return bookmarklet;
  }

  return { minify, stripComments };
});
