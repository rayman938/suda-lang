mod codegen;
mod lexer;
mod parser;
mod types;

pub use codegen::{emit_rust, CompileError};
pub use parser::{parse, Expr, Function, Program, Statement, Type};
pub use types::check;

pub fn compile(source: &str) -> Result<String, CompileError> {
    let program = parse(source)?;
    check(&program)?;
    emit_rust(&program)
}

#[cfg(test)]
mod tests {
    use super::compile;

    #[test]
    fn checks_and_lowers_a_typed_program() {
        let rust = compile(
            r#"
دالة اجمع(أ: عدد, ب: عدد) -> عدد {
    أرجع أ + ب;
}

دالة رئيسية() -> لا_شيء {
    دع نتيجة: عدد = اجمع(20, 22);
    اطبع(نتيجة);
}
"#,
        )
        .expect("valid typed Suda program");
        assert!(rust.contains("checked_add"));
        assert!(rust.contains("println!"));
        assert!(rust.contains("fn main"));
    }

    #[test]
    fn rejects_a_type_mismatch_before_codegen() {
        let error = compile(
            r#"
دالة رئيسية() -> لا_شيء {
    دع عدد: عدد = صحيح;
}
"#,
        )
        .expect_err("a boolean cannot initialize an integer");
        assert!(error.to_string().contains("نوع القيمة"));
    }

    #[test]
    fn rejects_undefined_names_and_wrong_argument_counts() {
        let undefined = compile(
            r#"
دالة رئيسية() -> لا_شيء {
    اطبع(مجهول);
}
"#,
        )
        .expect_err("undefined variables must be rejected");
        assert!(undefined.to_string().contains("غير معرّف"));

        let wrong_arguments = compile(
            r#"
دالة خذ(قيمة: عدد) -> عدد {
    أرجع قيمة;
}

دالة رئيسية() -> لا_شيء {
    اطبع(خذ());
}
"#,
        )
        .expect_err("calls must provide all declared arguments");
        assert!(wrong_arguments.to_string().contains("تحتاج 1 وسيطًا"));
    }

    #[test]
    fn requires_non_unit_functions_to_return_on_every_branch() {
        let error = compile(
            r#"
دالة قيمة(شرط: منطقي) -> عدد {
    إذا شرط {
        أرجع 1;
    } وإلا {
    }
}

دالة رئيسية() -> لا_شيء {
}
"#,
        )
        .expect_err("a non-unit function must return on all control-flow paths");
        assert!(error.to_string().contains("كل مسارات"));
    }

    #[test]
    fn lowers_conditionals_loops_and_text_values() {
        let rust = compile(
            r#"
دالة رئيسية() -> لا_شيء {
    دع رسالة: نص = "أهلاً";
    دع عداد: عدد = 0;
    طالما عداد < 2 {
        إذا صحيح {
            اطبع(رسالة);
        }
        عداد = عداد + 1;
    }
}
"#,
        )
        .expect("valid control flow and text");
        assert!(rust.contains("while"));
        assert!(rust.contains("if true"));
        assert!(rust.contains("String::from"));
        assert!(rust.contains("checked_add"));
    }
}
