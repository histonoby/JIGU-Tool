import streamlit as st
import pandas as pd
import socket
import struct
import io
import time
from datetime import datetime

# --- 共通の関数定義 ---
def create_command_packet(op_code, command_id, offset, data_size):
    # (この関数に変更はありません)
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
        return struct.pack('!BBBBBBBBBBBB', *packet_values)
    except struct.error:
        return None

# --- Session Stateの初期化 ---
if 'log_messages' not in st.session_state:
    st.session_state['log_messages'] = []
if 'received_data' not in st.session_state:
    st.session_state['received_data'] = None
if 'init_phase' not in st.session_state:
    st.session_state['init_phase'] = "未開始"
if 'init_logs' not in st.session_state:
    st.session_state['init_logs'] = []
# ▼▼▼【変更点】▼▼▼
# サーバーソケットをセッション状態で管理
if 'server_socket' not in st.session_state:
    st.session_state['server_socket'] = None
# ▲▲▲【変更点】▲▲▲

# --- タブの定義 ---
tab1, tab2 = st.tabs(["手動コマンド", "初期化シーケンス"])

# ==============================================================================
# --- タブ1: 手動コマンド ---
# (このタブのコードに変更はありません)
# ==============================================================================
with tab1:
    # (コードは前回のままなので省略)
    st.header("JIGUツール 🛠️") # プレースホルダーとしてヘッダーを設置

# ==============================================================================
# --- タブ2: 初期化シーケンス ---
# ==============================================================================
with tab2:
    st.header("初期化シーケンスモニター")
    st.caption("制御基板の起動シーケンスをモニタリングし、コマンドを自動送信します。")

    PHASE_MAP = {
        0x00000000: "INITIALIZE", 0x00000008: "STANDBY",
        0x0000002E: "RECONSTRUCT", 0x00000010: "IDLE",
    }

    def init_log(message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.init_logs.insert(0, f"[{timestamp}] {message}") # 新しいログを先頭に追加

    # --- UIレイアウト ---
    col1, col2 = st.columns(2)
    with col1:
        if st.button("待機開始", type="primary", disabled=(st.session_state.server_socket is not None)):
            try:
                # サーバーソケットを作成し、セッション状態に保存
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind(('127.0.0.1', 60201))
                server_socket.listen(5)
                st.session_state.server_socket = server_socket
                st.session_state.init_phase = "待機中"
                st.session_state.init_logs = []
                init_log("サーバー起動。基板からの接続を待機中...")
                st.rerun()
            except Exception as e:
                st.error(f"サーバーの起動に失敗しました: {e}")

    with col2:
        if st.button("リセット", disabled=(st.session_state.server_socket is None)):
            if st.session_state.server_socket:
                st.session_state.server_socket.close()
            st.session_state.server_socket = None
            st.session_state.init_phase = "未開始"
            st.session_state.init_logs = []
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

    for log in st.session_state.init_logs:
        log_placeholder.text(log)

    # --- サーバーが起動している場合のみ、接続をチェックする ---
    if st.session_state.server_socket:
        server_socket = st.session_state.server_socket
        server_socket.setblocking(0) # ノンブロッキングモードに設定

        try:
            conn, addr = server_socket.accept()
            with conn:
                init_log(f"基板から接続: {addr}")
                cmd_packet = conn.recv(12)
                data_packet = conn.recv(4)
                status_packet = conn.recv(4)
                
                if data_packet:
                    data_value = struct.unpack('!I', data_packet)[0]
                    new_phase = PHASE_MAP.get(data_value)
                    
                    if new_phase:
                        st.session_state.init_phase = new_phase
                        init_log(f"状態遷移報告を受信 -> {new_phase}")

                        # STANDBYになったら、RECONSTRUCT指令を送信
                        if new_phase == "STANDBY":
                            init_log("STANDBYを検出。RECONSTRUCT指令を基板に送信します...")
                            time.sleep(1)
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_s:
                                client_s.connect(('127.0.0.1', 60202))
                                cmd = create_command_packet(0x3B, 1, 0, 4)
                                data = struct.pack('!I', 0x0000002E)
                                client_s.sendall(cmd)
                                client_s.sendall(data)
                                client_s.recv(4) # 応答受信
                                init_log("状態遷移指令を送信完了。")
                        
                        # IDLEになったら完了
                        elif new_phase == "IDLE":
                            st.session_state.init_phase = "完了"
                            init_log("初期化シーケンス完了！")
                            # サーバーを閉じる
                            st.session_state.server_socket.close()
                            st.session_state.server_socket = None

            st.rerun() # UIを更新するために再実行

        except BlockingIOError:
            # 接続がまだない場合は何もせず、次の更新を待つ
            # ページが自動的にリフレッシュされることでポーリング（定期確認）を実現
            time.sleep(1) # CPU負荷を抑えるための短い待機
            st.rerun()
        except Exception as e:
            init_log(f"エラーが発生しました: {e}")
            st.session_state.init_phase = "エラー"
            st.session_state.server_socket.close()
            st.session_state.server_socket = None
            st.rerun()