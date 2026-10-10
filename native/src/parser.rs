use crate::lexer::{tokenize, Token, TokenKind};
use crate::CompileError;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Type {
    I8,
    I16,
    I32,
    I64,
    U8,
    U16,
    U32,
    U64,
    Bool,
    Text,
    Unit,
}

impl Type {
    fn parse(name: &str) -> Option<Self> {
        Some(match name {
            "عدد_صغير" | "i8" => Self::I8,
            "عدد_16" | "i16" => Self::I16,
            "عدد_32" | "i32" => Self::I32,
            "عدد" | "i64" => Self::I64,
            "طبيعي_صغير" | "u8" => Self::U8,
            "طبيعي_16" | "u16" => Self::U16,
            "طبيعي_32" | "u32" => Self::U32,
            "طبيعي" | "u64" => Self::U64,
            "منطقي" | "bool" => Self::Bool,
            "نص" | "String" => Self::Text,
            "لا_شيء" | "فراغ" | "()" => Self::Unit,
            _ => return None,
        })
    }

    pub(crate) fn rust_name(&self) -> &'static str {
        match self {
            Self::I8 => "i8",
            Self::I16 => "i16",
            Self::I32 => "i32",
            Self::I64 => "i64",
            Self::U8 => "u8",
            Self::U16 => "u16",
            Self::U32 => "u32",
            Self::U64 => "u64",
            Self::Bool => "bool",
            Self::Text => "String",
            Self::Unit => "()",
        }
    }

    pub(crate) fn is_integer(&self) -> bool {
        matches!(
            self,
            Self::I8
                | Self::I16
                | Self::I32
                | Self::I64
                | Self::U8
                | Self::U16
                | Self::U32
                | Self::U64
        )
    }
}

#[derive(Clone, Debug)]
pub struct Program {
    pub functions: Vec<Function>,
}

#[derive(Clone, Debug)]
pub struct Function {
    pub name: String,
    pub parameters: Vec<Parameter>,
    pub result: Type,
    pub body: Vec<Statement>,
    pub line: usize,
}

#[derive(Clone, Debug)]
pub struct Parameter {
    pub name: String,
    pub ty: Type,
}

#[derive(Clone, Debug)]
pub enum Statement {
    Let {
        name: String,
        ty: Type,
        value: Expr,
        line: usize,
    },
    Assign {
        name: String,
        value: Expr,
        line: usize,
    },
    Return {
        value: Option<Expr>,
        line: usize,
    },
    Expression {
        value: Expr,
        line: usize,
    },
    If {
        condition: Expr,
        yes: Vec<Statement>,
        no: Vec<Statement>,
        line: usize,
    },
    While {
        condition: Expr,
        body: Vec<Statement>,
        line: usize,
    },
    CountedLoop {
        name: String,
        start: Expr,
        end: Expr,
        body: Vec<Statement>,
        line: usize,
    },
}

#[derive(Clone, Debug)]
pub enum Expr {
    Integer(i128, usize),
    Boolean(bool, usize),
    Text(String, usize),
    Variable(String, usize),
    Call(String, Vec<Expr>, usize),
    Unary(String, Box<Expr>, usize),
    Binary(String, Box<Expr>, Box<Expr>, usize),
}

impl Expr {
    pub(crate) fn line(&self) -> usize {
        match self {
            Self::Integer(_, line)
            | Self::Boolean(_, line)
            | Self::Text(_, line)
            | Self::Variable(_, line)
            | Self::Call(_, _, line)
            | Self::Unary(_, _, line)
            | Self::Binary(_, _, _, line) => *line,
        }
    }
}

pub fn parse(source: &str) -> Result<Program, CompileError> {
    Parser {
        tokens: tokenize(source)?,
        cursor: 0,
    }
    .program()
}

struct Parser {
    tokens: Vec<Token>,
    cursor: usize,
}

impl Parser {
    fn current(&self) -> &Token {
        &self.tokens[self.cursor]
    }

    fn advance(&mut self) -> Token {
        let token = self.current().clone();
        if !matches!(token.kind, TokenKind::End) {
            self.cursor += 1;
        }
        token
    }

    fn identifier(&mut self, expected: &str) -> Result<(String, usize), CompileError> {
        let token = self.advance();
        if let TokenKind::Identifier(name) = token.kind {
            Ok((name, token.line))
        } else {
            Err(CompileError::new(token.line, expected))
        }
    }

    fn symbol(&mut self, expected: &str) -> Result<(), CompileError> {
        let token = self.advance();
        if token.kind == TokenKind::Symbol(expected.to_string()) {
            Ok(())
        } else {
            Err(CompileError::new(
                token.line,
                format!("متوقع الرمز «{expected}»."),
            ))
        }
    }

    fn keyword(&self, expected: &str) -> bool {
        matches!(&self.current().kind, TokenKind::Identifier(word) if word == expected)
    }

    fn program(mut self) -> Result<Program, CompileError> {
        let mut functions = Vec::new();
        while !matches!(self.current().kind, TokenKind::End) {
            functions.push(self.function()?);
        }
        if functions.is_empty() {
            return Err(CompileError::new(1, "البرنامج يحتاج دالة واحدة على الأقل."));
        }
        Ok(Program { functions })
    }

    fn function(&mut self) -> Result<Function, CompileError> {
        if !self.keyword("دالة") {
            return Err(CompileError::new(
                self.current().line,
                "التعريف الأعلى يجب أن يبدأ بكلمة «دالة».",
            ));
        }
        let line = self.advance().line;
        let (name, _) = self.identifier("اسم الدالة متوقع.")?;
        self.symbol("(")?;
        let mut parameters = Vec::new();
        if !self.at_symbol(")") {
            loop {
                let (parameter, _) = self.identifier("اسم الوسيط متوقع.")?;
                self.symbol(":")?;
                parameters.push(Parameter {
                    name: parameter,
                    ty: self.ty()?,
                });
                if self.at_symbol(")") {
                    break;
                }
                self.symbol(",")?;
            }
        }
        self.symbol(")")?;
        self.symbol("->")?;
        let result = self.ty()?;
        let body = self.block()?;
        Ok(Function {
            name,
            parameters,
            result,
            body,
            line,
        })
    }

    fn ty(&mut self) -> Result<Type, CompileError> {
        let token = self.advance();
        if let TokenKind::Identifier(name) = token.kind {
            Type::parse(&name)
                .ok_or_else(|| CompileError::new(token.line, format!("نوع غير معروف «{name}».")))
        } else {
            Err(CompileError::new(token.line, "اسم النوع متوقع."))
        }
    }

    fn block(&mut self) -> Result<Vec<Statement>, CompileError> {
        self.symbol("{")?;
        let mut statements = Vec::new();
        while !self.at_symbol("}") {
            if matches!(self.current().kind, TokenKind::End) {
                return Err(CompileError::new(self.current().line, "كتلة غير مغلقة."));
            }
            statements.push(self.statement()?);
        }
        self.symbol("}")?;
        Ok(statements)
    }

    fn statement(&mut self) -> Result<Statement, CompileError> {
        let line = self.current().line;
        if self.keyword("دع") {
            self.advance();
            let (name, _) = self.identifier("اسم المتغير متوقع.")?;
            self.symbol(":")?;
            let ty = self.ty()?;
            self.symbol("=")?;
            let value = self.expression(0)?;
            self.symbol(";")?;
            return Ok(Statement::Let {
                name,
                ty,
                value,
                line,
            });
        }
        if self.keyword("أرجع") || self.keyword("ارجع") {
            self.advance();
            let value = if self.at_symbol(";") {
                None
            } else {
                Some(self.expression(0)?)
            };
            self.symbol(";")?;
            return Ok(Statement::Return { value, line });
        }
        if self.keyword("إذا") || self.keyword("اذا") {
            self.advance();
            let condition = self.expression(0)?;
            let yes = self.block()?;
            let no = if self.keyword("وإلا") || self.keyword("والا") {
                self.advance();
                self.block()?
            } else {
                Vec::new()
            };
            return Ok(Statement::If {
                condition,
                yes,
                no,
                line,
            });
        }
        if self.keyword("طالما") {
            self.advance();
            let condition = self.expression(0)?;
            let body = self.block()?;
            return Ok(Statement::While {
                condition,
                body,
                line,
            });
        }
        if self.keyword("كرر") {
            self.advance();
            let (name, _) = self.identifier("اسم متغير الحلقة متوقع.")?;
            if !self.keyword("من") {
                return Err(CompileError::new(
                    self.current().line,
                    "متوقع «من» بعد اسم الحلقة.",
                ));
            }
            self.advance();
            let start = self.expression(0)?;
            if !self.keyword("إلى") && !self.keyword("الى") {
                return Err(CompileError::new(
                    self.current().line,
                    "متوقع «إلى» قبل نهاية الحلقة.",
                ));
            }
            self.advance();
            let end = self.expression(0)?;
            let body = self.block()?;
            return Ok(Statement::CountedLoop {
                name,
                start,
                end,
                body,
                line,
            });
        }

        let expression = self.expression(0)?;
        if self.at_symbol("=") {
            self.advance();
            let Expr::Variable(name, _) = expression else {
                return Err(CompileError::new(line, "الإسناد يحتاج اسم متغير."));
            };
            let value = self.expression(0)?;
            self.symbol(";")?;
            return Ok(Statement::Assign { name, value, line });
        }
        self.symbol(";")?;
        Ok(Statement::Expression {
            value: expression,
            line,
        })
    }

    fn expression(&mut self, minimum: u8) -> Result<Expr, CompileError> {
        let mut left = self.prefix()?;
        loop {
            if self.at_symbol("(") {
                let line = left.line();
                let Expr::Variable(name, _) = left else {
                    return Err(CompileError::new(line, "يمكن استدعاء الدوال المسماة فقط."));
                };
                self.advance();
                let mut arguments = Vec::new();
                if !self.at_symbol(")") {
                    loop {
                        arguments.push(self.expression(0)?);
                        if self.at_symbol(")") {
                            break;
                        }
                        self.symbol(",")?;
                    }
                }
                self.symbol(")")?;
                left = Expr::Call(name, arguments, line);
                continue;
            }
            let Some((precedence, operator)) = self.binary_operator() else {
                break;
            };
            if precedence < minimum {
                break;
            }
            let line = self.advance().line;
            let right = self.expression(precedence + 1)?;
            left = Expr::Binary(operator, Box::new(left), Box::new(right), line);
        }
        Ok(left)
    }

    fn prefix(&mut self) -> Result<Expr, CompileError> {
        let token = self.advance();
        match token.kind {
            TokenKind::Integer(text) => {
                let value = text
                    .parse::<i128>()
                    .map_err(|_| CompileError::new(token.line, "العدد خارج حدود الصيغة."))?;
                Ok(Expr::Integer(value, token.line))
            }
            TokenKind::Text(value) => Ok(Expr::Text(value, token.line)),
            TokenKind::Identifier(name) => match name.as_str() {
                "صحيح" => Ok(Expr::Boolean(true, token.line)),
                "خطأ" => Ok(Expr::Boolean(false, token.line)),
                "ليس" => Ok(Expr::Unary(name, Box::new(self.expression(7)?), token.line)),
                _ => Ok(Expr::Variable(name, token.line)),
            },
            TokenKind::Symbol(symbol) if symbol == "-" || symbol == "+" => Ok(Expr::Unary(
                symbol,
                Box::new(self.expression(7)?),
                token.line,
            )),
            TokenKind::Symbol(symbol) if symbol == "(" => {
                let expression = self.expression(0)?;
                self.symbol(")")?;
                Ok(expression)
            }
            _ => Err(CompileError::new(token.line, "بداية تعبير غير صالحة.")),
        }
    }

    fn binary_operator(&self) -> Option<(u8, String)> {
        let TokenKind::Symbol(symbol) = &self.current().kind else {
            if let TokenKind::Identifier(word) = &self.current().kind {
                return match word.as_str() {
                    "و" => Some((2, word.clone())),
                    "أو" | "او" => Some((1, "أو".into())),
                    _ => None,
                };
            }
            return None;
        };
        let precedence = match symbol.as_str() {
            "==" | "!=" | "<" | "<=" | ">" | ">=" => 3,
            "+" | "-" => 4,
            "*" | "/" | "%" => 5,
            _ => return None,
        };
        Some((precedence, symbol.clone()))
    }

    fn at_symbol(&self, expected: &str) -> bool {
        self.current().kind == TokenKind::Symbol(expected.to_string())
    }
}
