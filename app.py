import streamlit as st
import pandas as pd
import socket
import struct
import io
import time
from datetime import datetime

# --- 共通の関数定義 ---
def create_command_packet(op_code, command_id, offset, data_size):
    try:
        offset_b2 = (offset >> 16) & 0xFF; offset_b1 = (offset >> 8) & 0xFF; offset_b0 = offset & 0xFF
        size_b2 = (data_size >> 16) & 0xFF; size_b1 = (data_size >> 8) & 0xFF; size_b0 = data_size & 0xFF
        packet_values = (op_code, 0x00, command_id, offset_b2, offset_b1, offset_b0, size_b2, size_b1, size_b0, 0x00, 0x00, 0x00)
        return struct.pack('!BBBBBBBBBBBB', *packet_values)
    except: return None

# --- Session Stateの初期化 ---
if 'log_messages' not in st.session_state: st.session_state['log_messages'] = []
if 'received_data' not in st.session_state: st.session_state['received_data'] = None
if 'init_phase' not in st.session_state: st.session_state['init_phase'] = "未開始"
if 'init_logs' not in st.session_state: st.session_state['init_logs'] = []
if 'init_server_socket' not in st.session_state: st.session_state['init_server_socket'] = None
if 'ls_phase' not in st.session_state: st.session_state['ls_phase'] = "未開始"
if 'ls_logs' not in st.session_state: st.session_state['ls_logs'] = []
if 'ls_server_socket' not in st.session_state: st.session_state['ls_server_socket'] = None
if 'ls_scan_data' not in st.session_state: st.session_state['ls_scan_data'] = None

tab1, tab2, tab3 = st.tabs(["手動コマンド", "初期化シーケンス", "ラインスキャン"])

# ==============================================================================
# --- タブ1: 手動コマンド ---
# ==============================================================================
with tab1:
    st.header("手動コマンド実行")
    st.info("ℹ️ この機能のテストには、ターミナルで `mock_server.py` を起動してください。")
    
    def log_message(level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.log_messages.insert(0, (level, f"[{timestamp}] {message}"))

    def display_logs(container):
        for level, message in st.session_state.log_messages:
            if level == "info": container.info(message)
            elif level == "success": container.success(message)
            elif level == "warning": container.warning(message)
            elif level == "error": container.error(message)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("1. 接続先設定")
        ip_address = st.text_input("IPアドレス", "127.0.0.1", key="manual_ip")
        port = st.number_input("ポート番号", 1, 65535, 60200, key="manual_port")
        st.subheader("2. コマンド設定")
        op_code_option = st.radio("オペレーションコード", ["書き込み (0x3B)", "読み出し (0x3C)"], horizontal=True, key="op_code")
        op_code = 0x3B if "書き込み" in op_code_option else 0x3C
        is_write_command = (op_code == 0x3B)
        command_id = st.number_input("コマンドID", 0, 255, 1, key="manual_cmd_id")
        max_24bit = (2**24) - 1
        offset = st.number_input("オフセット", 0, max_24bit, 0, key="manual_offset")
        st.subheader("3. データ設定")
        if is_write_command:
            uploaded_file = st.file_uploader("送信するCSVファイルを選択", type=['csv'])
            data_size_label = "書き込みデータサイズ (bytes)"
        else:
            output_filename = st.text_input("ダウンロードファイル名", "received_data.bin")
            data_size_label = "読み出しデータサイズ (bytes)"
        data_size = st.number_input(data_size_label, 0, max_24bit, 1024, key="manual_size")
        send_button = st.button("コマンドを送信", type="primary", key="manual_send")
    
    with col2:
        st.subheader("ログ")
        log_area = st.container(height=400, border=True)
        display_logs(log_area)
        if st.session_state['received_data']:
            st.download_button("受信データをダウンロード", st.session_state['received_data'], output_filename, 'application/octet-stream')

    if send_button:
        st.session_state.log_messages = []
        st.session_state.received_data = None
        log_message("info", f"処理を開始します... ターゲット: {ip_address}:{port}")
        command_packet = create_command_packet(op_code, command_id, offset, data_size)
        if command_packet:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(5)
                    s.connect((ip_address, port))
                    s.sendall(command_packet)
                    if is_write_command:
                        df = pd.read_csv(uploaded_file)
                        data_to_send = df.to_csv(index=False).encode('utf-8')[:data_size]
                        s.sendall(data_to_send)
                    else:
                        received_data = b''
                        while len(received_data) < data_size:
                            chunk = s.recv(min(data_size - len(received_data), 4096))
                            if not chunk: break
                            received_data += chunk
                        st.session_state.received_data = received_data
                    status = s.recv(4)
                    log_message("success", f"コマンド成功。ステータス: {status.hex()}")
            except Exception as e:
                log_message("error", f"エラー: {e}")
        st.rerun()

# ==============================================================================
# --- タブ2: 初期化シーケンス ---
# ==============================================================================
with tab2:
    st.header("初期化シーケンスモニター")
    st.info("ℹ️ この機能のテストには、ターミナルで `mock_board_init.py` を起動してください。")
    # (コードは前回から変更なし)
    PHASE_MAP = { 0x00000000: "INITIALIZE", 0x00000008: "STANDBY", 0x0000002E: "RECONSTRUCT", 0x00000010: "IDLE" }
    def init_log(message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.init_logs.insert(0, f"[{timestamp}] {message}")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("待機開始", type="primary", disabled=(st.session_state.init_server_socket is not None), key="start_init"):
            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind(('127.0.0.1', 60201)); server_socket.listen(5)
                st.session_state.init_server_socket = server_socket
                st.session_state.init_phase = "待機中"; st.session_state.init_logs = []
                init_log("サーバー起動。基板からの接続を待機中...")
                st.rerun()
            except Exception as e: st.error(f"サーバーの起動に失敗: {e}")
    with col2:
        if st.button("リセット", disabled=(st.session_state.init_server_socket is None), key="reset_init"):
            if st.session_state.init_server_socket: st.session_state.init_server_socket.close()
            st.session_state.init_server_socket = None
            st.session_state.init_phase = "未開始"; st.session_state.init_logs = []
            st.rerun()
    st.divider()
    status_placeholder = st.empty()
    log_placeholder = st.container(height=400, border=True)
    with status_placeholder.container():
        st.subheader("現在の制御基板フェーズ")
        phase = st.session_state.init_phase
        if phase == "未開始": st.info("「待機開始」ボタンを押してください。")
        elif phase == "完了": st.success("✅ 初期化シーケンスが正常に完了しました。")
        elif phase == "エラー": st.error("❌ エラーが発生しました。ログを確認してください。")
        else: st.warning(f"⏳ {phase}")
    for log in st.session_state.init_logs: log_placeholder.text(log)
    if st.session_state.init_server_socket:
        server_socket = st.session_state.init_server_socket
        server_socket.setblocking(0)
        try:
            conn, addr = server_socket.accept()
            with conn:
                init_log(f"基板から接続: {addr}")
                cmd_packet = conn.recv(12); data_packet = conn.recv(4); status_packet = conn.recv(4)
                if data_packet:
                    data_value = struct.unpack('!I', data_packet)[0]
                    new_phase = PHASE_MAP.get(data_value)
                    if new_phase:
                        st.session_state.init_phase = new_phase
                        init_log(f"状態遷移報告を受信 -> {new_phase}")
                        if new_phase == "STANDBY":
                            init_log("STANDBY検出。RECONSTRUCT指令を基板に送信します...")
                            time.sleep(1)
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_s:
                                client_s.connect(('127.0.0.1', 60202))
                                cmd = create_command_packet(0x3B, 1, 0, 4); data = struct.pack('!I', 0x2E)
                                client_s.sendall(cmd); client_s.sendall(data); client_s.recv(4)
                                init_log("状態遷移指令を送信完了。")
                        elif new_phase == "IDLE":
                            st.session_state.init_phase = "完了"; init_log("初期化シーケンス完了！")
                            st.session_state.init_server_socket.close(); st.session_state.init_server_socket = None
            st.rerun()
        except BlockingIOError: time.sleep(1); st.rerun()
        except Exception as e:
            init_log(f"エラー: {e}"); st.session_state.init_phase = "エラー"
            if st.session_state.init_server_socket: st.session_state.init_server_socket.close()
            st.session_state.init_server_socket = None
            st.rerun()

# ==============================================================================
# --- タブ3: ラインスキャン ---
# ==============================================================================
with tab3:
    st.header("ラインスキャンシーケンス")
    st.caption("ラインスキャンのシーケンスを実行・モニタリングします。")
    st.info("ℹ️ この機能のテストには、ターミナルで `mock_board_linescan.py` を起動してください。")

    # ▼▼▼【変更点】ステージコントローラへのコマンド送信関数を追加 ▼▼▼
    def ls_log(message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.ls_logs.insert(0, f"[{timestamp}] {message}")

    def send_stage_command(ip, port, command):
        """ステージコントローラにコマンドを送信し、応答を確認する"""
        try:
            ls_log(f"ステージ ({ip}:{port}) へ接続します...")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stage_socket:
                stage_socket.settimeout(10) # タイムアウトを10秒に設定
                stage_socket.connect((ip, port))
                
                # コマンドはASCII文字列で、終端にキャリッジリターン(\r)を付与
                full_command = (command + '\r').encode('ascii')
                stage_socket.sendall(full_command)
                ls_log(f"コマンド送信: {command}")
                
                # 応答を受信
                response = stage_socket.recv(1024).decode('ascii').strip()
                ls_log(f"応答受信: {response}")
                
                if "OK" in response:
                    return True
                else:
                    ls_log(f"エラー: ステージから予期せぬ応答がありました。 ({response})")
                    return False
        except socket.timeout:
            ls_log(f"エラー: ステージへの接続がタイムアウトしました。")
            return False
        except ConnectionRefusedError:
            ls_log(f"エラー: ステージへの接続が拒否されました。IP/ポートを確認してください。")
            return False
        except Exception as e:
            ls_log(f"エラー: ステージとの通信中に予期せぬエラーが発生しました。 {e}")
            return False
    # ▲▲▲【変更点】▲▲▲

    # --- UIレイアウト ---
    st.subheader("設定")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**制御基板**")
        param_data = st.number_input("スキャンパラメータ (ID:0x14のデータ)", value=0x12345678, format="%08X", key="ls_param")
    with c2:
        # ▼▼▼【変更点】ステージコントローラの設定項目を追加 ▼▼▼
        st.markdown("**ステージコントローラ (FC-511)**")
        stage_ip = st.text_input("IPアドレス", "192.168.0.200", key="stage_ip")
        stage_port = st.number_input("ポート番号", 1, 65535, 8000, key="stage_port")
        axis_num = st.number_input("軸番号", 1, 2, 1, key="stage_axis")
        pulse_count = st.number_input("測定移動パルス数", 0, 1000000, 50000, key="stage_pulse")
        # ▲▲▲【変更点】▲▲▲

    col1, col2 = st.columns(2)
    with col1:
        if st.button("スキャン開始", type="primary", disabled=(st.session_state.ls_server_socket is not None), key="start_ls"):
            # (スキャン開始のロジックは前回と同じ)
            # ...
            pass
    with col2:
        if st.button("リセット", disabled=(st.session_state.ls_server_socket is None), key="reset_linescan"):
            # (リセットのロジックは前回と同じ)
            # ...
            pass
            
    st.divider()
    status_placeholder = st.empty()
    log_placeholder = st.container(height=400, border=True)

    with status_placeholder.container():
        st.subheader("現在のシーケンスフェーズ")
        phase = st.session_state.ls_phase
        if phase == "未開始": st.info("パラメータを確認し、「スキャン開始」ボタンを押してください。")
        elif phase == "完了": st.success("✅ ラインスキャンが正常に完了しました。")
        else: st.warning(f"⏳ {phase}")
    for log in st.session_state.ls_logs: log_placeholder.text(log)
    if st.session_state.ls_scan_data:
        st.download_button("スキャンデータをダウンロード", st.session_state.ls_scan_data, "scan_data.bin", "application/octet-stream", key="ls_download")

    # --- サーバーが起動している場合の接続チェックとシーケンス実行 ---
    if st.session_state.ls_server_socket:
        server = st.session_state.ls_server_socket
        server.setblocking(0)
        try:
            conn, addr = server.accept()
            with conn:
                # (基板からのコマンド受信部分は変更なし)
                conn.recv(1); cmd_id = struct.unpack("!B", conn.recv(1))[0]; conn.recv(7); data = struct.unpack("!I", conn.recv(4))[0]; conn.recv(4)
                ls_log(f"基板からコマンド受信 - ID:{hex(cmd_id)}, Data:{hex(data)}")

                # 4. ステージ助走位置移動依頼を受信
                if cmd_id == 0x05:
                    st.session_state.ls_phase = "ステージ助走位置へ移動中..."
                    ls_log("ステージへ原点復帰命令を発行します。")
                    # ▼▼▼【変更点】実際のステージコマンド送信に置き換え ▼▼▼
                    success1 = send_stage_command(stage_ip, stage_port, f"H:{axis_num}")
                    time.sleep(0.1) # コマンド間に短いウェイト
                    success2 = send_stage_command(stage_ip, stage_port, "G")
                    
                    if success1 and success2:
                        ls_log("ステージの原点復帰命令 成功。")
                        # 5. 基板へステージ助走位置移動完了を返信
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect(('127.0.0.1', 60202))
                            s.sendall(create_command_packet(0x3B, 0x09, 0, 4) + struct.pack('!I', 0))
                            s.recv(4)
                            ls_log("基板へ助走位置移動完了(ID:0x09)を送信しました。")
                    else:
                        ls_log("エラー: ステージの原点復帰に失敗しました。シーケンスを中断します。")
                        st.session_state.ls_phase = "エラー"
                    # ▲▲▲【変更点】▲▲▲

                # 6. ステージ測定移動依頼を受信
                elif cmd_id == 0x06:
                    st.session_state.ls_phase = "ステージ測定位置へ移動中..."
                    ls_log("ステージへ測定移動指令を発行します。")
                    # ▼▼▼【変更点】実際のステージコマンド送信に置き換え ▼▼▼
                    move_command = f"M:{axis_num}+P{pulse_count}"
                    success1 = send_stage_command(stage_ip, stage_port, move_command)
                    time.sleep(0.1)
                    success2 = send_stage_command(stage_ip, stage_port, "G")

                    if success1 and success2:
                        ls_log("ステージの測定移動命令 成功。")
                        # 7. 基板へステージ測定移動完了を返信
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect(('127.0.0.1', 60202))
                            s.sendall(create_command_packet(0x3B, 0x0A, 0, 4) + struct.pack('!I', 0))
                            s.recv(4)
                            ls_log("基板へ測定移動完了(ID:0x0A)を送信しました。")
                    else:
                        ls_log("エラー: ステージの測定移動に失敗しました。シーケンスを中断します。")
                        st.session_state.ls_phase = "エラー"
                    # ▲▲▲【変更点】▲▲▲

                # (以降のロジックは前回と同じ)
                # ...

            st.rerun()

        except BlockingIOError:
            time.sleep(1)
            st.rerun()
        except Exception as e:
            ls_log(f"エラー: {e}")
            if st.session_state.ls_server_socket: st.session_state.ls_server_socket.close()
            st.session_state.ls_server_socket = None
            st.session_state.ls_phase = "エラー"
            st.rerun()
