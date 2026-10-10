use crate::CompileError;

#[derive(Clone, Debug, PartialEq)]
pub(crate) enum TokenKind {
    Identifier(String),
    Integer(String),
    Text(String),
    Symbol(String),
    End,
}

#[derive(Clone, Debug)]
pub(crate) struct Token {
    pub kind: TokenKind,
    pub line: usize,
}

pub(crate) fn tokenize(source: &str) -> Result<Vec<Token>, CompileError> {
    let mut chars = source.chars().peekable();
    let mut line = 1;
    let mut tokens = Vec::new();

    while let Some(ch) = chars.next() {
        match ch {
            '\n' => line += 1,
            c if c.is_whitespace() => {}
            '#' => {
                for rest in chars.by_ref() {
                    if rest == '\n' {
                        line += 1;
                        break;
                    }
                }
            }
            '"' => {
                let start_line = line;
                let mut value = String::new();
                let mut closed = false;
                while let Some(next) = chars.next() {
                    match next {
                        '"' => {
                            closed = true;
                            break;
                        }
                        '\n' => return Err(CompileError::new(line, "النص لا يجوز أن يعبر سطرًا.")),
                        '\\' => {
                            let escaped = chars.next().ok_or_else(|| {
                                CompileError::new(start_line, "نص غير مكتمل بعد محرف الهروب.")
                            })?;
                            value.push(match escaped {
                                'n' => '\n',
                                'r' => '\r',
                                't' => '\t',
                                '"' => '"',
                                '\\' => '\\',
                                _ => {
                                    return Err(CompileError::new(
                                        start_line,
                                        "محرف هروب غير معروف داخل النص.",
                                    ))
                                }
                            });
                        }
                        other => value.push(other),
                    }
                }
                if !closed {
                    return Err(CompileError::new(start_line, "نص غير مغلق."));
                }
                tokens.push(Token {
                    kind: TokenKind::Text(value),
                    line: start_line,
                });
            }
            c if c.is_ascii_digit() => {
                let mut value = c.to_string();
                while let Some(next) = chars.peek() {
                    if next.is_ascii_digit() {
                        value.push(chars.next().expect("peeked character exists"));
                    } else {
                        break;
                    }
                }
                tokens.push(Token {
                    kind: TokenKind::Integer(value),
                    line,
                });
            }
            c if is_identifier_start(c) => {
                let mut value = c.to_string();
                while let Some(next) = chars.peek() {
                    if is_identifier_continue(*next) {
                        value.push(chars.next().expect("peeked character exists"));
                    } else {
                        break;
                    }
                }
                tokens.push(Token {
                    kind: TokenKind::Identifier(value),
                    line,
                });
            }
            '-' if chars.peek() == Some(&'>') => {
                chars.next();
                tokens.push(Token {
                    kind: TokenKind::Symbol("->".into()),
                    line,
                });
            }
            '=' | '!' | '<' | '>' if chars.peek() == Some(&'=') => {
                let mut operator = ch.to_string();
                operator.push(chars.next().expect("peeked character exists"));
                tokens.push(Token {
                    kind: TokenKind::Symbol(operator),
                    line,
                });
            }
            '+' | '-' | '*' | '/' | '%' | '=' | '!' | '<' | '>' | '(' | ')' | '{' | '}' | ':'
            | ';' | ',' => tokens.push(Token {
                kind: TokenKind::Symbol(ch.to_string()),
                line,
            }),
            _ => return Err(CompileError::new(line, format!("رمز غير مدعوم: {ch:?}."))),
        }
    }

    tokens.push(Token {
        kind: TokenKind::End,
        line,
    });
    Ok(tokens)
}

fn is_identifier_start(ch: char) -> bool {
    ch == '_' || ch.is_alphabetic()
}

fn is_identifier_continue(ch: char) -> bool {
    ch == '_' || ch.is_alphanumeric()
}
