%{
%}

%token WORD
%token LITERAL
%left '-' '+'
%left '*' '/'
%precedence NEG
%right '^'
%token RETURN "return"
%token NAMESPACE "namespace"

%start input

%%

input:
  %empty
| input Statement
;

Statement:
  Declaration ';'
| Expression ';'
;

ReturnStatement:
  RETURN Expression ';'
;

Declaration:
  Identity
| Identity '=' Scope
| Identity '=' Expression
;

Scope:
 '{' '}'
| '{' ScopeInner '}'
;

ScopeInner:
  %empty
| ScopeInner Statement
| ScopeInner ReturnStatement
;

Expression:
  Operator
| Atom;

Atom:
  LITERAL
| WORD
| '(' Expression ')'
;

Operator:
  Atom '+' Atom
| Atom '-' Atom
| Atom '*' Atom
| Atom '/' Atom
| '-' Atom %prec NEG
| Atom '^' Atom
;

Identity:
  WORD ':' "namespace"
| WORD ':' Type
;

Type:
  WORD
| WORD TypeMods
;

TypeMods:
  %empty
| TypeMods ArrayDef
| TypeMods ParamList
;

ArrayDef:
  '[' ']'
| '[' LITERAL ']'
;

ParamList:
  '(' ')'
| '(' Identities ')'
;

Identities:
  %empty
| Identities ',' Identity
;

%%

//