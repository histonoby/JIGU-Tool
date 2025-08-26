import streamlit as st
import pandas as pd
import socket
import struct
import io

# --- 関数定義 --- (変更なし)
def create_command_packet(op_code: int, command_id: int, offset: int, data_size: int) -> bytes:
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
        st.error(f"コマンドパケットの生成に失敗しました: {e}")
        return None

# --- Streamlit UI ---

st.set_page_config(page_title="JIGUツール", layout="wide")
st.title("JIGUツール 🛠️")
st.caption("制御基板・ステージコントローラ制御アプリケーション")

if 'received_data' not in st.session_state:
    st.session_state['received_data'] = None

col1, col2 = st.columns([1, 1])

with col1:
    st.header("1. 接続先設定")
    # ▼▼▼【変更点】▼▼▼
    # 接続先IPアドレスのデフォルト値を '127.0.0.1' に変更
    ip_address = st.text_input("IPアドレス", "127.0.0.1")
    # ▲▲▲【変更点】▲▲▲
    port = st.number_input("ポート番号", min_value=1, max_value=65535, value=60200)

    # --- 以下、UIの変更なし ---
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
        st.session_state['received_data'] = None
    else:
        output_filename = st.text_input("ダウンロードファイル名", "received_data.bin")
        data_size_label = "読み出しデータサイズ (bytes)"
        uploaded_file = None
    data_size = st.number_input(data_size_label, min_value=0, max_value=max_24bit, value=1024, step=1)
    send_button = st.button("コマンドを送信", type="primary")

with col2:
    st.header("ログ")
    log_area = st.container()
    if st.session_state['received_data']:
        st.divider()
        st.subheader("📥 データダウンロード")
        st.download_button(label="受信データをダウンロード", data=st.session_state['received_data'], file_name=output_filename, mime='application/octet-stream')

# --- ボタンが押されたときの処理 --- (変更なし)
if send_button:
    st.session_state['received_data'] = None
    if not ip_address or not port:
        log_area.error("IPアドレスとポート番号を入力してください。")
    elif is_write_command and not uploaded_file:
        log_area.error("書き込みコマンドにはCSVファイルをアップロードしてください。")
    else:
        log_area.info(f"処理を開始します... ターゲット: {ip_address}:{port}")
        command_packet = create_command_packet(op_code, command_id, offset, data_size)
        if command_packet:
            log_area.info(f"生成されたコマンドパケット (16進数): {command_packet.hex(' ')}")
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(10)
                    log_area.info("サーバーへ接続します...")
                    s.connect((ip_address, port))
                    log_area.success("サーバーへの接続が完了しました。")
                    s.sendall(command_packet)
                    log_area.info("コマンドパケットを送信しました。")
                    if is_write_command:
                        df = pd.read_csv(uploaded_file)
                        csv_data_bytes = df.to_csv(index=False).encode('utf-8')
                        data_to_send = csv_data_bytes[:data_size]
                        s.sendall(data_to_send)
                        log_area.info(f"{len(data_to_send)} bytes のデータパケットを送信しました。")
                        log_area.info("サーバーからのステータス応答を待っています...")
                        status_packet = s.recv(4)
                        if len(status_packet) == 4:
                            status_value = struct.unpack('!I', status_packet)[0]
                            log_area.info(f"4バイトのステータスを受信しました: {hex(status_value)}")
                            if status_value == 0:
                                log_area.success("書き込みコマンドが正常に完了しました。")
                            else:
                                log_area.error(f"エラー応答を受信しました: {hex(status_value)}")
                        else:
                            log_area.warning("サーバーから正常なステータス応答がありませんでした。")
                    else:
                        log_area.info(f"{data_size} bytes のデータ受信を開始します...")
                        received_data = b''
                        bytes_to_receive = data_size
                        while len(received_data) < bytes_to_receive:
                            remaining = bytes_to_receive - len(received_data)
                            chunk = s.recv(min(remaining, 4096))
                            if not chunk: break
                            received_data += chunk
                        log_area.success(f"合計 {len(received_data)} bytes のデータを受信しました。")
                        st.session_state['received_data'] = received_data
                        log_area.info("ダウンロードの準備ができました。")
            except Exception as e:
                log_area.error(f"通信中にエラーが発生しました: {e}")