
import re
from typing import List, Optional, Tuple, Union

# Token types for lexing
TOKEN_TYPES = {
    'WHITESPACE': r'\s+',
    'LBRACKET': r'\[',
    'RBRACKET': r'\]',
    'LPAREN': r'\(',
    'RPAREN': r'\)',
    'AND': r'&',
    'OR': r'\|',
    'NOT': r'!',
    'EQUALS': r'=',
    'STAR': r'\*',
    'PLUS': r'\+',
    'QUESTION': r'\?',
    'WORD': r'word|lemma|tag|entity|chunk|incoming|outgoing|mention',
    'STRING': r'\".*?\"|\'.*?\'|\w+',
    'NUMBER': r'\d+',
    'AT': r'@',
    'COLON': r':',
    'CAPTURE_START': r'\(\?<',
    'CAPTURE_END': r'\)',
    'START_ASSERT': r'\^',
    'END_ASSERT': r'\$',
    'LOOKAHEAD_START': r'\(\?=|\(\?!',
    'LOOKAHEAD_END': r'\)',
    # Add any other necessary tokens here
}

# Types for tokens and parsed elements
Token = Tuple[str, str]
ASTNode = Union[str, Tuple, List]

# Lexer for breaking input into tokens
class Lexer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens: List[Token] = []
        self.tokenize()

    def tokenize(self) -> None:
        pos = 0
        while pos < len(self.text):
            match = None
            for token_type, regex in TOKEN_TYPES.items():
                pattern = re.compile(regex)
                match = pattern.match(self.text, pos)
                if match:
                    # Skip whitespace tokens, do not add them to the token list
                    if token_type != 'WHITESPACE':
                        self.tokens.append((token_type, match.group()))
                    pos = match.end()
                    break
            if not match:
                raise SyntaxError(f"Unknown character: {self.text[pos]}")
    
    def next_token(self) -> Optional[Token]:
        return self.tokens.pop(0) if self.tokens else None

# Parser for Token Constraints and Patterns
class TokenConstraintParser:
    def __init__(self, lexer: Lexer) -> None:
        self.lexer = lexer
        self.current_token: Optional[Token] = self.lexer.next_token()

    def eat(self, token_type: str) -> None:
        if self.current_token and self.current_token[0] == token_type:
            self.current_token = self.lexer.next_token()
        else:
            expected = token_type
            got = self.current_token[0] if self.current_token else 'EOF'
            raise SyntaxError(f"Expected {expected} but got {got}")

    def parse(self) -> Optional[ASTNode]:
        return self.token_constraint()

    def token_constraint(self) -> Optional[ASTNode]:
        # TokenConstraint ::= ‘[’ [DisjunctiveConstraint] ‘]’
        self.eat('LBRACKET')
        constraint = None
        if self.current_token and self.current_token[0] != 'RBRACKET':
            constraint = self.disjunctive_constraint()
        self.eat('RBRACKET')
        return constraint

    def disjunctive_constraint(self) -> ASTNode:
        # DisjunctiveConstraint ::= ConjunctiveConstraint ( ‘|’ ConjunctiveConstraint )*
        left = self.conjunctive_constraint()
        while self.current_token and self.current_token[0] == 'OR':
            self.eat('OR')
            right = self.conjunctive_constraint()
            left = ('OR', left, right)
        return left

    def conjunctive_constraint(self) -> ASTNode:
        # ConjunctiveConstraint ::= NegatedConstraint ( ‘&’ NegatedConstraint )*
        left = self.negated_constraint()
        while self.current_token and self.current_token[0] == 'AND':
            self.eat('AND')
            right = self.negated_constraint()
            left = ('AND', left, right)
        return left

    def negated_constraint(self) -> ASTNode:
        # NegatedConstraint ::= [ ‘!’ ] AtomicConstraint
        if self.current_token and self.current_token[0] == 'NOT':
            self.eat('NOT')
            return ('NOT', self.atomic_constraint())
        else:
            return self.atomic_constraint()

    def atomic_constraint(self) -> ASTNode:
        # AtomicConstraint ::= FieldConstraint | ‘(’ DisjunctiveConstraint ‘)’
        if self.current_token and self.current_token[0] == 'WORD':
            return self.field_constraint()
        elif self.current_token and self.current_token[0] == 'LPAREN':
            self.eat('LPAREN')
            disjunction = self.disjunctive_constraint()
            self.eat('RPAREN')
            return disjunction
        else:
            raise SyntaxError("Expected FieldConstraint or nested DisjunctiveConstraint")

    def field_constraint(self) -> ASTNode:
        # FieldConstraint ::= FieldName ‘=’ StringMatcher
        field_name = self.current_token[1]
        self.eat('WORD')
        self.eat('EQUALS')
        string_matcher = self.string_matcher()
        return ('FIELD', field_name, string_matcher)

    def string_matcher(self) -> ASTNode:
        # StringMatcher ::= ExactStringMatcher | RegexStringMatcher
        if self.current_token and self.current_token[0] == 'STRING':
            literal = self.current_token[1]
            self.eat('STRING')
            return ('EXACT', literal)
        else:
            raise SyntaxError("Expected string")

# Token Pattern Parser
class TokenPatternParser(TokenConstraintParser):
    def parse_token_pattern(self) -> ASTNode:
        return self.disjunctive_token_pattern()

    def disjunctive_token_pattern(self) -> ASTNode:
        # DisjunctiveTokenPattern ::= ConcatenatedTokenPattern ( ‘|’ ConcatenatedTokenPattern )*
        left = self.concatenated_token_pattern()
        while self.current_token and self.current_token[0] == 'OR':
            self.eat('OR')
            right = self.concatenated_token_pattern()
            left = ('OR', left, right)
        return left

    def concatenated_token_pattern(self) -> ASTNode:
        # ConcatenatedTokenPattern ::= QuantifiedTokenPattern QuantifiedTokenPattern*
        patterns = [self.quantified_token_pattern()]
        while self.current_token and self.current_token[0] in ('WORD', 'LPAREN', 'AT', 'CAPTURE_START', 'LBRACKET'):
            patterns.append(self.quantified_token_pattern())
        if len(patterns) == 1:
            return patterns[0]
        else:
            return ('SEQ', patterns)

    def quantified_token_pattern(self) -> ASTNode:
        # QuantifiedTokenPattern ::= AtomicTokenPattern [Quantifier]
        atom = self.atomic_token_pattern()
        if self.current_token and self.current_token[0] in ('STAR', 'PLUS', 'QUESTION'):
            quantifier = self.current_token[1]
            self.eat(self.current_token[0])
            return ('QUANT', atom, quantifier)
        return atom

    def atomic_token_pattern(self) -> ASTNode:
        # AtomicTokenPattern ::= SingleTokenPattern | MentionTokenPattern | CaptureTokenPattern | AssertionTokenPattern
        if self.current_token and self.current_token[0] == 'WORD':
            return self.field_constraint()
        elif self.current_token and self.current_token[0] == 'LBRACKET':
            return self.token_constraint()
        elif self.current_token and self.current_token[0] == 'LPAREN':
            self.eat('LPAREN')
            pattern = self.disjunctive_token_pattern()
            self.eat('RPAREN')
            return pattern
        elif self.current_token and self.current_token[0] == 'AT':
            return self.mention_token_pattern()
        elif self.current_token and self.current_token[0] == 'CAPTURE_START':
            return self.capture_token_pattern()
        else:
            raise SyntaxError(f"Unexpected token '{self.current_token[1] if self.current_token else 'EOF'}' in AtomicTokenPattern")

    def mention_token_pattern(self) -> ASTNode:
        # MentionTokenPattern ::= ‘@’ [ StringLiteral ‘:’ ] ExactStringMatcher
        self.eat('AT')
        if self.current_token and self.current_token[0] == 'STRING':
            mention = self.string_matcher()
        else:
            mention = None
        return ('MENTION', mention)

    def capture_token_pattern(self) -> ASTNode:
        # CaptureTokenPattern ::= ‘(?<’ identifier ‘>’ DisjunctiveTokenPattern ‘)’
        self.eat('CAPTURE_START')
        capture_name = self.current_token[1]
        self.eat('STRING')  # identifier
        self.eat('CAPTURE_END')
        pattern = self.disjunctive_token_pattern()
        return ('CAPTURE', capture_name, pattern)

# Example usage
if __name__ == "__main__":
    text = '[word="hello" & lemma="greet"] | @Person'
    lexer = Lexer(text)
    # Debug: Print tokens
    print("Tokens:")
    for token in lexer.tokens:
        print(token)
    parser = TokenPatternParser(lexer)
    result = parser.parse_token_pattern()
    print("\nParsed AST:")
    print(result)
