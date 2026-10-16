import {evaluatePolicy} from './evaluator.ts';
let text='';for await (const chunk of process.stdin) text+=chunk;
const {request,rules}=JSON.parse(text);
console.log(JSON.stringify(evaluatePolicy(request,rules,'enforce')));
