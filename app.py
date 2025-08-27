import streamlit as st
import pandas as pd
import socket
import struct
import io
from datetime import datetime

# --- Session Stateの初期化 ---
# 画面を再描画しても値を保持したい変数を定義
if 'received_data' not in st.session_state:
    st.session_state['received_data'] = None
if 'log_messages' not in st.session_state:
    st.session_state['log_messages'] = []

# --- 関数定義 ---

def create_command_packet(op_code: int, command_id: int, offset: int, data_size: int) -> bytes:
    """指定されたパラメータに基づいて12バイトのコマンドパケットを生成します。"""
    try:
        offset_b2 = (offset >> 16) & 0xFF
        offset_b1 = (offset >> 8) & 0xFF
        offset_b0 = offset & 0xFF
        size_b2 = (data_size >> 16) & 0xFF
        size_b1 = (data_size >> 8) & 0xFF
        size_b0 = data_size & 0xFF
        packet_values = (
            op_code, 0x00, command_id,
            offset_b2, offset_b1, offset_b0,
            size_b2, size_b1, size_b0,
            0x00, 0x00, 0x00
        )
        packet = struct.pack('!BBBBBBBBBBBB', *packet_values)
        return packet
    except struct.error as e:
        log_message("error", f"コマンドパケットの生成に失敗しました: {e}")
        return None

# ▼▼▼【変更点】▼▼▼
def log_message(level, message):
    """ログを画面とSession Stateの両方に追加する関数"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    full_message = f"[{timestamp}] {message}"
    
    # Session Stateにログを追加
    st.session_state.log_messages.append((level, full_message))

def display_logs(container):
    """Session Stateに保存されたログを画面に表示する関数"""
    for level, message in st.session_state.log_messages:
        if level == "info":
            container.info(message)
        elif level == "success":
            container.success(message)
        elif level == "warning":
            container.warning(message)
        elif level == "error":
            container.error(message)
# ▲▲▲【変更点】▲▲▲

# --- Streamlit UI ---

st.set_page_config(page_title="JIGUツール", layout="wide")
st.title("JIGUツール 🛠️")
st.caption("制御基板・ステージコントローラ制御アプリケーション")

col1, col2 = st.columns([1, 1])

with col1:
    # (UI部分の変更なし)
    st.header("1. 接続先設定")
    ip_address = st.text_input("IPアドレス", "127.0.0.1")
    port = st.number_input("ポート番号", min_value=1, max_value=65535, value=60200)
    st.header("2. コマンド設定")
    op_code_option = st.radio("オペレーションコード", ["書き込み (0x3B)", "読み出し (0x3C)"], horizontal=True, key="op_code_selector")
    op_code = 0x3B if op_code_option == "書き込み (0x3B)" else 0x3C
    is_write_command = (op_code == 0x3B)
    command_id = st.number_input("コマンドID", min_value=0, max_value=255, value=1, step=1)
    max_24bit = (2**24) - 1
    offset = st.number_input("オフセット", min_value=0, max_value=max_24bit, value=0, step=1)
    st.header("3. データ設定")
    if is_write_command:
        uploaded_file = st.file_uploader("送信するCSVファイルを選択", type=['csv'])
        data_size_label = "書き込みデータサイズ (bytes)"
    else:
        output_filename = st.text_input("ダウンロードファイル名", "received_data.bin")
        data_size_label = "読み出しデータサイズ (bytes)"
        uploaded_file = None
    data_size = st.number_input(data_size_label, min_value=0, max_value=max_24bit, value=1024, step=1)
    
    send_button = st.button("コマンドを送信", type="primary")

with col2:
    st.header("ログ")
    log_area = st.container()
    
    # ▼▼▼【変更点】▼▼▼
    # ログ表示関数を呼び出す
    display_logs(log_area)
    # ▲▲▲【変更点】▲▲▲
    
    if st.session_state['received_data']:
        st.divider()
        st.subheader("📥 データダウンロード")
        st.download_button(label="受信データをダウンロード", data=st.session_state['received_data'], file_name=output_filename, mime='application/octet-stream')

# --- ボタンが押されたときの処理 ---
if send_button:
    # 実行時に過去のログとデータをクリア
    st.session_state['received_data'] = None
    st.session_state['log_messages'] = []
    
    # バリデーションチェック（ログ関数を使用）
    valid = True
    if not ip_address or not port:
        log_message("error", "IPアドレスとポート番号を入力してください。")
        valid = False
    if is_write_command and not uploaded_file:
        log_message("error", "書き込みコマンドにはCSVファイルをアップロードしてください。")
        valid = False
    
    if valid:
        log_message("info", f"処理を開始します... ターゲット: {ip_address}:{port}")
        command_packet = create_command_packet(op_code, command_id, offset, data_size)
        
        if command_packet:
            log_message("info", f"生成されたコマンドパケット (16進数): {command_packet.hex(' ')}")
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(10)
                    log_message("info", "サーバーへ接続します...")
                    s.connect((ip_address, port))
                    log_message("success", "サーバーへの接続が完了しました。")
                    
                    s.sendall(command_packet)
                    log_message("info", "コマンドパケットを送信しました。")
                    
                    if is_write_command:
                        df = pd.read_csv(uploaded_file)
                        csv_data_bytes = df.to_csv(index=False).encode('utf-8')
                        data_to_send = csv_data_bytes[:data_size]
                        s.sendall(data_to_send)
                        log_message("info", f"{len(data_to_send)} bytes のデータパケットを送信しました。")
                        
                        log_message("info", "サーバーからのステータス応答を待っています...")
                        status_packet = s.recv(4)
                        if len(status_packet) == 4:
                            status_value = struct.unpack('!I', status_packet)[0]
                            log_message("info", f"4バイトのステータスを受信しました: {hex(status_value)}")
                            if status_value == 0:
                                log_message("success", "書き込みコマンドが正常に完了しました。")
                            else:
                                log_message("error", f"エラー応答を受信しました: {hex(status_value)}")
                        else:
                            log_message("warning", "サーバーから正常なステータス応答がありませんでした。")
                    
                    else: # 読み出し処理
                        log_message("info", f"{data_size} bytes のデータ受信を開始します...")
                        received_data = b''
                        while len(received_data) < data_size:
                            chunk = s.recv(min(data_size - len(received_data), 4096))
                            if not chunk: break
                            received_data += chunk
                        
                        log_message("success", f"合計 {len(received_data)} bytes のデータを受信しました。")
                        st.session_state['received_data'] = received_data
                        
                        log_message("info", "サーバーからのステータス応答を待っています...")
                        status_packet = s.recv(4)
                        if len(status_packet) == 4:
                            status_value = struct.unpack('!I', status_packet)[0]
                            log_message("info", f"4バイトのステータスを受信しました: {hex(status_value)}")
                            if status_value == 0:
                                log_message("success", "読み出しコマンドが正常に完了しました。")
                                log_message("info", "ダウンロードの準備ができました。")
                                st.rerun() # UIを更新してボタンを表示
                            else:
                                log_message("error", f"エラー応答を受信しました: {hex(status_value)}")
                        else:
                            log_message("warning", "サーバーから正常なステータス応答がありませんでした。")

            except Exception as e:
                log_message("error", f"通信中にエラーが発生しました: {e}")
    
    # ログを反映させるために再実行
    st.rerun()