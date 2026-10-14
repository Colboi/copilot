use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, State, WindowEvent};

const BACKEND_PORT: u16 = 37651;
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct BackendState {
    child: Mutex<Option<Child>>,
    port: u16,
}

fn tray_icon() -> tauri::image::Image<'static> {
    tauri::image::Image::from_bytes(include_bytes!("../icons/colpilot-icon.png"))
        .expect("ColPilot icon PNG could not be decoded")
}

fn show_main_window(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        eprintln!("Main window was not found");
        return;
    };

    if let Err(error) = window.show() {
        eprintln!("Main window show failed: {error}");
    }
    if let Err(error) = window.unminimize() {
        eprintln!("Main window restore failed: {error}");
    }
    if let Err(error) = window.set_focus() {
        eprintln!("Main window focus failed: {error}");
    }
}

fn start_backend(app: &AppHandle) -> Result<Child, Box<dyn std::error::Error>> {
    let project_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .ok_or("Project root is unavailable")?
        .to_path_buf();
    let executable_root = std::env::current_exe()?
        .parent()
        .map(Path::to_path_buf)
        .ok_or("Executable directory is unavailable")?;

    let source_backend_script = project_root.join("backend").join("main.py");
    let portable_backend_script = executable_root.join("backend").join("main.py");
    let backend_script = if cfg!(debug_assertions) {
        source_backend_script.clone()
    } else if portable_backend_script.exists() {
        portable_backend_script.clone()
    } else {
        let bundled_backend_script = app.path().resource_dir()?.join("backend").join("main.py");
        if bundled_backend_script.exists() {
            bundled_backend_script
        } else {
            source_backend_script
        }
    };

    if !backend_script.exists() {
        return Err(format!("Backend script does not exist: {}", backend_script.display()).into());
    }

    let portable_runtime_root = executable_root.join("runtime");
    let portable_python = portable_runtime_root.join("python.exe");
    let virtual_environment_python = project_root
        .join(".venv")
        .join("Scripts")
        .join("python.exe");
    let uses_portable_runtime = !cfg!(debug_assertions) && portable_python.exists();
    let python_program = if uses_portable_runtime {
        portable_python
    } else if virtual_environment_python.exists() {
        virtual_environment_python
    } else {
        PathBuf::from("python")
    };

    let working_root = if portable_backend_script.exists() {
        executable_root
    } else {
        project_root
    };

    let mut command = Command::new(python_program);
    command
        .arg(backend_script)
        .arg("--port")
        .arg(BACKEND_PORT.to_string())
        .current_dir(working_root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .creation_flags(CREATE_NO_WINDOW);

    if uses_portable_runtime {
        let runtime_library_bin = portable_runtime_root.join("Library").join("bin");
        let mut path_entries = vec![portable_runtime_root, runtime_library_bin];
        if let Some(current_path) = std::env::var_os("PATH") {
            path_entries.extend(std::env::split_paths(&current_path));
        }
        command.env("PATH", std::env::join_paths(path_entries)?);
    }

    Ok(command.spawn()?)
}

fn request_backend_exit(port: u16) {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(600))
        .build()
        .expect("Failed to create backend HTTP client");

    let result = client
        .post(format!("http://127.0.0.1:{port}/api/commands"))
        .json(&serde_json::json!({ "command": "exit" }))
        .send();

    if let Err(error) = result {
        eprintln!("Backend exit command failed: {error}");
    }
}

fn stop_backend(state: &BackendState) {
    let mut child_slot = state.child.lock().expect("Backend state lock is poisoned");
    if let Some(mut child) = child_slot.take() {
        if let Err(error) = child.kill() {
            eprintln!("Backend process termination failed: {error}");
        }
        if let Err(error) = child.wait() {
            eprintln!("Backend process wait failed: {error}");
        }
    }
}

fn monitor_backend(app: AppHandle) {
    std::thread::spawn(move || loop {
        let backend_exited = {
            let state = app.state::<BackendState>();
            let mut child_slot = state.child.lock().expect("Backend state lock is poisoned");

            match child_slot.as_mut() {
                Some(child) => match child.try_wait() {
                    Ok(Some(status)) => {
                        eprintln!("Backend process exited with status: {status}");
                        child_slot.take();
                        true
                    }
                    Ok(None) => false,
                    Err(error) => {
                        eprintln!("Backend process status check failed: {error}");
                        child_slot.take();
                        true
                    }
                },
                None => true,
            }
        };

        if backend_exited {
            app.exit(0);
            break;
        }

        std::thread::sleep(Duration::from_millis(100));
    });
}

fn shutdown_app(app: &AppHandle) {
    let state = app.state::<BackendState>();
    request_backend_exit(state.port);
    stop_backend(&state);
    app.exit(0);
}

#[tauri::command]
fn get_backend_url(state: State<'_, BackendState>) -> String {
    format!("http://127.0.0.1:{}", state.port)
}

#[tauri::command]
fn exit_app(app: AppHandle) {
    shutdown_app(&app);
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let backend = start_backend(app.handle())?;
            app.manage(BackendState {
                child: Mutex::new(Some(backend)),
                port: BACKEND_PORT,
            });
            monitor_backend(app.handle().clone());

            let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&quit_item])?;

            TrayIconBuilder::new()
                .menu(&menu)
                .icon(tray_icon())
                .tooltip("Colpilot")
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| {
                    if event.id() == "quit" {
                        shutdown_app(app);
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main_window(tray.app_handle());
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() != "main" {
                return;
            }

            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                if let Err(error) = window.hide() {
                    eprintln!("Main window hide failed: {error}");
                }
            }
        })
        .invoke_handler(tauri::generate_handler![get_backend_url, exit_app])
        .run(tauri::generate_context!())
        .expect("Error while running Colpilot");
}
