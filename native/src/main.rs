use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

use suda_native::compile;

fn main() -> ExitCode {
    match run(env::args().skip(1).collect()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("خطأ: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run(arguments: Vec<String>) -> Result<(), String> {
    let Some(command) = arguments.first().map(String::as_str) else {
        return Err(usage());
    };
    if command == "--help" || command == "-h" {
        println!("{}", usage());
        return Ok(());
    }
    if !matches!(command, "check" | "emit-rust" | "build") {
        return Err(usage());
    }
    let source_path = arguments.get(1).ok_or_else(usage)?;
    let source = fs::read_to_string(source_path)
        .map_err(|error| format!("تعذرت قراءة «{source_path}»: {error}"))?;
    let rust_source = compile(&source).map_err(|error| error.to_string())?;

    match command {
        "check" => {
            println!("سليم الأنواع: {source_path}");
            Ok(())
        }
        "emit-rust" => {
            let output_path = output_argument(&arguments)?;
            write_output(&output_path, &rust_source)?;
            println!("أُنشئ مصدر Rust الوسيط: {}", output_path.display());
            Ok(())
        }
        "build" => {
            let output_path = output_argument(&arguments)?;
            let target = target_argument(&arguments)?;
            compile_executable(&rust_source, &output_path, target.as_deref())
        }
        _ => Err(usage()),
    }
}

fn output_argument(arguments: &[String]) -> Result<PathBuf, String> {
    let output_index = arguments
        .iter()
        .position(|argument| argument == "-o" || argument == "--output")
        .ok_or_else(|| "استخدم -o لتحديد ملف الخرج.".to_string())?;
    arguments
        .get(output_index + 1)
        .map(PathBuf::from)
        .ok_or_else(|| "مسار ملف الخرج مفقود.".to_string())
}

fn target_argument(arguments: &[String]) -> Result<Option<String>, String> {
    let Some(target_index) = arguments
        .iter()
        .position(|argument| argument == "--target" || argument == "-t")
    else {
        return Ok(None);
    };
    arguments
        .get(target_index + 1)
        .filter(|target| !target.starts_with('-'))
        .cloned()
        .map(Some)
        .ok_or_else(|| "اسم الهدف مفقود بعد --target.".to_string())
}

fn write_output(path: &Path, content: &str) -> Result<(), String> {
    ensure_parent_directory(path)?;
    fs::write(path, content).map_err(|error| format!("تعذرت كتابة ملف الخرج: {error}"))
}

fn ensure_parent_directory(path: &Path) -> Result<(), String> {
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        fs::create_dir_all(parent).map_err(|error| format!("تعذر إنشاء مجلد الخرج: {error}"))?;
    }
    Ok(())
}

fn compile_executable(
    rust_source: &str,
    output_path: &Path,
    target: Option<&str>,
) -> Result<(), String> {
    ensure_parent_directory(output_path)?;
    let mut generated_source = env::temp_dir();
    generated_source.push(format!(
        "suda_native_{}_{}.rs",
        std::process::id(),
        TEMPORARY_FILE_ID.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
    ));
    write_output(&generated_source, rust_source)?;

    let mut command = Command::new(env::var_os("RUSTC").unwrap_or_else(|| "rustc".into()));
    command
        .arg("--edition=2021")
        .arg("--crate-type=bin")
        .arg("-C")
        .arg("opt-level=2")
        .arg("--crate-name=suda_program")
        .arg(&generated_source)
        .arg("-o")
        .arg(output_path);
    if let Some(target) = target {
        command.arg("--target").arg(target);
    }
    let result = command.output();
    fs::remove_file(&generated_source)
        .map_err(|error| format!("تعذر حذف المصدر الوسيط المؤقت: {error}"))?;
    let result = result.map_err(|error| format!("تعذر تشغيل rustc: {error}"))?;
    if !result.status.success() {
        let details = String::from_utf8_lossy(&result.stderr);
        return Err(format!("فشل بناء البرنامج التنفيذي:\n{details}"));
    }
    println!("أُنشئ البرنامج التنفيذي: {}", output_path.display());
    Ok(())
}

static TEMPORARY_FILE_ID: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);

fn usage() -> String {
    "مترجم سُدى منخفض المستوى — مبني بـRust\n\
الأوامر:\n\
  suda-native check <ملف.sada>\n\
  suda-native emit-rust <ملف.sada> -o <ملف.rs>\n\
  suda-native build <ملف.sada> -o <برنامج> [--target <الهدف>]\n\
يتطلب build تثبيت Rust stable ورابطًا مناسبًا للهدف؛ يبني برنامجًا تنفيذيًا."
        .to_string()
}
