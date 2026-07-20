use std::io::{Read, Write};
use std::net::TcpStream;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::Manager;

const BACKEND_PORT: u16 = 5050;
const BACKEND_TIMEOUT: u64 = 30;

struct BackendProcess(Mutex<Option<Child>>);

impl Drop for BackendProcess {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(ref mut child) = *guard {
                let _ = child.kill();
                let _ = child.wait();
                eprintln!("[Luna Desktop] Backend encerrado");
            }
        }
    }
}

fn find_project_root() -> Option<std::path::PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let mut dir = exe.parent()?;
    for _ in 0..10 {
        if dir.join("start.sh").exists() || dir.join("api.py").exists() {
            return Some(dir.to_path_buf());
        }
        dir = dir.parent()?;
    }
    None
}

fn start_backend() -> Option<Child> {
    let root = find_project_root()?;
    let script = root.join("start.sh");

    eprintln!("[Luna Desktop] Iniciando backend em: {:?}", root);

    match Command::new("bash")
        .arg(&script)
        .current_dir(&root)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => {
            eprintln!("[Luna Desktop] Backend iniciado (PID {})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[Luna Desktop] Erro ao iniciar backend: {}", e);
            None
        }
    }
}

fn wait_for_backend() -> bool {
    let deadline = Instant::now() + Duration::from_secs(BACKEND_TIMEOUT);
    while Instant::now() < deadline {
        if let Ok(mut stream) = TcpStream::connect_timeout(
            &format!("127.0.0.1:{}", BACKEND_PORT).parse().unwrap(),
            Duration::from_secs(1),
        ) {
            let mut buf = [0; 1024];
            if stream
                .write_all(b"GET /api/health HTTP/1.0\r\n\r\n")
                .is_ok()
                && stream.read(&mut buf).is_ok()
            {
                let resp = String::from_utf8_lossy(&buf);
                if resp.contains("200 OK") {
                    eprintln!("[Luna Desktop] Backend pronto!");
                    return true;
                }
            }
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    eprintln!(
        "[Luna Desktop] Timeout aguardando backend ({}s)",
        BACKEND_TIMEOUT
    );
    false
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let child = start_backend();
            if child.is_some() {
                wait_for_backend();
            }
            app.manage(BackendProcess(Mutex::new(child)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
