use std::collections::HashMap;

use crate::codegen::CompileError;
use crate::parser::{Expr, Function, Program, Statement, Type};

type Signatures = HashMap<String, (Vec<Type>, Type)>;
type Scope = HashMap<String, Type>;

pub fn check(program: &Program) -> Result<(), CompileError> {
    let mut signatures = Signatures::new();
    let mut entry = None;

    for (index, function) in program.functions.iter().enumerate() {
        if signatures.contains_key(&function.name) || function.name == "اطبع" {
            return Err(CompileError::new(
                function.line,
                format!("اسم الدالة «{}» مكرر أو محجوز.", function.name),
            ));
        }
        if function.name == "رئيسية" {
            entry = Some(index);
        }
        signatures.insert(
            function.name.clone(),
            (
                function
                    .parameters
                    .iter()
                    .map(|parameter| parameter.ty.clone())
                    .collect(),
                function.result.clone(),
            ),
        );
    }

    let entry = entry.ok_or_else(|| CompileError::new(1, "الدالة «رئيسية» مطلوبة."))?;
    let entry_function = &program.functions[entry];
    if !entry_function.parameters.is_empty() || entry_function.result != Type::Unit {
        return Err(CompileError::new(
            entry_function.line,
            "«رئيسية» يجب أن تكون بلا وسائط وترجع «لا_شيء».",
        ));
    }

    for function in &program.functions {
        check_function(function, &signatures)?;
    }
    Ok(())
}

fn check_function(function: &Function, signatures: &Signatures) -> Result<(), CompileError> {
    let mut root = Scope::new();
    for parameter in &function.parameters {
        if root
            .insert(parameter.name.clone(), parameter.ty.clone())
            .is_some()
        {
            return Err(CompileError::new(
                function.line,
                format!("اسم الوسيط «{}» مكرر.", parameter.name),
            ));
        }
        if parameter.ty == Type::Unit {
            return Err(CompileError::new(
                function.line,
                "لا يمكن تعريف وسيط من النوع «لا_شيء».",
            ));
        }
    }
    let mut scopes = vec![root];
    check_statements(&function.body, &mut scopes, signatures, &function.result)?;

    if function.result != Type::Unit && !always_returns(&function.body) {
        return Err(CompileError::new(
            function.line,
            format!("كل مسارات الدالة «{}» يجب أن تنتهي بأرجع.", function.name),
        ));
    }
    Ok(())
}

fn check_statements(
    statements: &[Statement],
    scopes: &mut Vec<Scope>,
    signatures: &Signatures,
    return_type: &Type,
) -> Result<(), CompileError> {
    for statement in statements {
        match statement {
            Statement::Let {
                name,
                ty,
                value,
                line,
            } => {
                if ty == &Type::Unit {
                    return Err(CompileError::new(
                        *line,
                        "لا يمكن تخزين قيمة من النوع «لا_شيء».",
                    ));
                }
                let actual = infer(value, scopes, signatures, Some(ty))?;
                require_same(ty, &actual, *line)?;
                let scope = scopes.last_mut().expect("function scope exists");
                if scope.contains_key(name) {
                    return Err(CompileError::new(
                        *line,
                        format!("المتغير «{name}» معرّف مسبقًا في هذا النطاق."),
                    ));
                }
                scope.insert(name.clone(), ty.clone());
            }
            Statement::Assign { name, value, line } => {
                let expected = lookup(scopes, name)
                    .ok_or_else(|| CompileError::new(*line, format!("اسم غير معرّف «{name}».")))?;
                let actual = infer(value, scopes, signatures, Some(&expected))?;
                require_same(&expected, &actual, *line)?;
            }
            Statement::Return { value, line } => match (return_type, value) {
                (Type::Unit, None) => {}
                (Type::Unit, Some(_)) => {
                    return Err(CompileError::new(*line, "دالة «لا_شيء» لا ترجع قيمة."))
                }
                (_, None) => {
                    return Err(CompileError::new(*line, "قيمة الإرجاع مطلوبة لهذه الدالة."))
                }
                (expected, Some(expression)) => {
                    let actual = infer(expression, scopes, signatures, Some(expected))?;
                    require_same(expected, &actual, *line)?;
                }
            },
            Statement::Expression { value, line } => {
                infer(value, scopes, signatures, None)?;
                if !matches!(value, Expr::Call(_, _, _)) {
                    return Err(CompileError::new(
                        *line,
                        "التعبير كعبارة يجب أن يكون استدعاء دالة.",
                    ));
                }
            }
            Statement::If {
                condition,
                yes,
                no,
                line,
            } => {
                let condition_type = infer(condition, scopes, signatures, Some(&Type::Bool))?;
                require_same(&Type::Bool, &condition_type, *line)?;
                scopes.push(Scope::new());
                check_statements(yes, scopes, signatures, return_type)?;
                scopes.pop();
                scopes.push(Scope::new());
                check_statements(no, scopes, signatures, return_type)?;
                scopes.pop();
            }
            Statement::While {
                condition,
                body,
                line,
            } => {
                let condition_type = infer(condition, scopes, signatures, Some(&Type::Bool))?;
                require_same(&Type::Bool, &condition_type, *line)?;
                scopes.push(Scope::new());
                check_statements(body, scopes, signatures, return_type)?;
                scopes.pop();
            }
            Statement::CountedLoop {
                name,
                start,
                end,
                body,
                line,
            } => {
                let start_type = infer(start, scopes, signatures, Some(&Type::I64))?;
                let end_type = infer(end, scopes, signatures, Some(&Type::I64))?;
                require_same(&Type::I64, &start_type, *line)?;
                require_same(&Type::I64, &end_type, *line)?;
                let mut loop_scope = Scope::new();
                loop_scope.insert(name.clone(), Type::I64);
                scopes.push(loop_scope);
                check_statements(body, scopes, signatures, return_type)?;
                scopes.pop();
            }
        }
    }
    Ok(())
}

fn infer(
    expression: &Expr,
    scopes: &[Scope],
    signatures: &Signatures,
    expected: Option<&Type>,
) -> Result<Type, CompileError> {
    let line = expression.line();
    let actual = match expression {
        Expr::Integer(value, _) => {
            let ty = expected
                .filter(|ty| ty.is_integer())
                .cloned()
                .unwrap_or(Type::I64);
            if !integer_fits(*value, &ty) {
                return Err(CompileError::new(
                    line,
                    format!("العدد خارج مجال النوع {}.", ty.rust_name()),
                ));
            }
            ty
        }
        Expr::Boolean(_, _) => Type::Bool,
        Expr::Text(_, _) => Type::Text,
        Expr::Variable(name, _) => lookup(scopes, name)
            .ok_or_else(|| CompileError::new(line, format!("اسم غير معرّف «{name}».")))?,
        Expr::Call(name, arguments, _) if name == "اطبع" => {
            if arguments.len() != 1 {
                return Err(CompileError::new(
                    line,
                    "اطبع يقبل قيمة واحدة في هذا الإصدار.",
                ));
            }
            let value_type = infer(&arguments[0], scopes, signatures, None)?;
            if value_type == Type::Unit {
                return Err(CompileError::new(line, "لا يمكن طباعة قيمة «لا_شيء»."));
            }
            Type::Unit
        }
        Expr::Call(name, arguments, _) => {
            let (parameters, result) = signatures
                .get(name)
                .ok_or_else(|| CompileError::new(line, format!("دالة غير معرّفة «{name}».")))?;
            if parameters.len() != arguments.len() {
                return Err(CompileError::new(
                    line,
                    format!("الدالة «{name}» تحتاج {} وسيطًا.", parameters.len()),
                ));
            }
            for (argument, parameter) in arguments.iter().zip(parameters) {
                let argument_type = infer(argument, scopes, signatures, Some(parameter))?;
                require_same(parameter, &argument_type, argument.line())?;
            }
            result.clone()
        }
        Expr::Unary(operator, operand, _) => {
            let operand_type = infer(operand, scopes, signatures, expected)?;
            match operator.as_str() {
                "-" if is_signed_integer(&operand_type) => operand_type,
                "+" if operand_type.is_integer() => operand_type,
                "ليس" if operand_type == Type::Bool => Type::Bool,
                "-" | "+" => {
                    return Err(CompileError::new(line, "العامل الأحادي لا يقبل هذا النوع."))
                }
                _ => return Err(CompileError::new(line, "عامل أحادي غير معروف.")),
            }
        }
        Expr::Binary(operator, left, right, _) => {
            let operand_expected = match operator.as_str() {
                "+" | "-" | "*" | "/" | "%" => expected.filter(|ty| ty.is_integer()),
                "و" | "أو" => expected.filter(|ty| **ty == Type::Bool),
                _ => None,
            };
            let left_type = infer(left, scopes, signatures, operand_expected)?;
            let right_type = infer(right, scopes, signatures, Some(&left_type))?;
            require_same(&left_type, &right_type, line)?;
            match operator.as_str() {
                "و" | "أو" if left_type == Type::Bool => Type::Bool,
                "==" | "!=" if comparable(&left_type) => Type::Bool,
                "<" | "<=" | ">" | ">=" if left_type.is_integer() || left_type == Type::Text => {
                    Type::Bool
                }
                "+" | "-" | "*" | "/" | "%" if left_type.is_integer() => left_type,
                _ => {
                    return Err(CompileError::new(
                        line,
                        format!("العامل «{operator}» غير مدعوم لهذا النوع."),
                    ))
                }
            }
        }
    };
    if let Some(expected) = expected {
        require_same(expected, &actual, line)?;
    }
    Ok(actual)
}

fn lookup(scopes: &[Scope], name: &str) -> Option<Type> {
    scopes
        .iter()
        .rev()
        .find_map(|scope| scope.get(name).cloned())
}

fn require_same(expected: &Type, actual: &Type, line: usize) -> Result<(), CompileError> {
    if expected == actual {
        Ok(())
    } else {
        Err(CompileError::new(
            line,
            format!(
                "نوع القيمة {} لا يطابق النوع المطلوب {}.",
                actual.rust_name(),
                expected.rust_name()
            ),
        ))
    }
}

fn integer_fits(value: i128, ty: &Type) -> bool {
    match ty {
        Type::I8 => i8::try_from(value).is_ok(),
        Type::I16 => i16::try_from(value).is_ok(),
        Type::I32 => i32::try_from(value).is_ok(),
        Type::I64 => i64::try_from(value).is_ok(),
        Type::U8 => u8::try_from(value).is_ok(),
        Type::U16 => u16::try_from(value).is_ok(),
        Type::U32 => u32::try_from(value).is_ok(),
        Type::U64 => u64::try_from(value).is_ok(),
        _ => false,
    }
}

fn is_signed_integer(ty: &Type) -> bool {
    matches!(ty, Type::I8 | Type::I16 | Type::I32 | Type::I64)
}

fn comparable(ty: &Type) -> bool {
    ty.is_integer() || matches!(ty, Type::Bool | Type::Text)
}

fn always_returns(statements: &[Statement]) -> bool {
    statements.last().is_some_and(|statement| match statement {
        Statement::Return { .. } => true,
        Statement::If { yes, no, .. } => {
            !no.is_empty() && always_returns(yes) && always_returns(no)
        }
        _ => false,
    })
}
