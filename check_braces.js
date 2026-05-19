const fs = require('fs');
const code = fs.readFileSync('temp.js', 'utf8');
let lineNum = 1;
let openBraces = [];
let openParens = [];
let inString = false;
let stringChar = '';
let inComment = false;
let inMultiComment = false;

for (let i = 0; i < code.length; i++) {
  const c = code[i];
  const next = code[i+1];
  
  if (c === '\n') {
    lineNum++;
    inComment = false;
  }
  
  if (inComment) continue;
  if (inMultiComment) {
    if (c === '*' && next === '/') {
      inMultiComment = false;
      i++;
    }
    continue;
  }
  
  if (!inString) {
    if (c === '/' && next === '/') {
      inComment = true;
      i++;
      continue;
    }
    if (c === '/' && next === '*') {
      inMultiComment = true;
      i++;
      continue;
    }
    if (c === '\'' || c === '\"' || c === '\`') {
      inString = true;
      stringChar = c;
      continue;
    }
    if (c === '{') openBraces.push(lineNum);
    if (c === '}') {
      if (openBraces.length > 0) openBraces.pop();
    }
    if (c === '(') openParens.push(lineNum);
    if (c === ')') {
      if (openParens.length > 0) openParens.pop();
    }
  } else {
    if (c === '\\') {
      i++; // skip escaped char
      continue;
    }
    if (c === stringChar) {
      inString = false;
    }
  }
}
console.log('Unclosed strings?', inString);
console.log('Unclosed /* comments?', inMultiComment);
console.log('Unclosed braces at lines:', openBraces.slice(-10));
console.log('Unclosed parens at lines:', openParens.slice(-10));
