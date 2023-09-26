Identifier: [a-zA-Z];
Number: [0-9](_.0-9)+;
Literal: String | Number;
Comment: '/' '*' ... '*' '/' | '//' ... '\n';

Atom: Literal | Identifier | '(' Expression ')';
Infix: Atom ('+'|'-'|'/'|'*'|',') Atom;
Expression: Infix | Atom;
ReturnStatement: 'return' Expression;
ParamList: '(' Identity [',' Identity[...]] ')';
ArrayDef: '[' [Number] ']';
Type_: Identifier ( ArrayDef | ParamList )*;
Identity: Identifier ':' ('namespace' | Type_);

Declaration: Identity [ '=' Expression | Scope ];
Statement: Declaration | Expression;
Scope: LBrace (Statement | ReturnStatement)* RBrace;
Document: Statement* EOF;





