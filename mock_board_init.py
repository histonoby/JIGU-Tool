import socket
import struct
import time
import threading

# --- 共通の関数と定数 ---
HOST_APP_IP = '127.0.0.1'
HOST_APP_PORT = 60201 # アプリのサーバーポート
BOARD_SERVER_PORT = 60202 # 基板自身のサーバーポート

def create_command_packet(op_code, command_id, offset, data_size):
    # (app.pyと同じ関数)
    try:
        offset_b2 = (offset >> 16) & 0xFF; offset_b1 = (offset >> 8) & 0xFF; offset_b0 = offset & 0xFF
        size_b2 = (data_size >> 16) & 0xFF; size_b1 = (data_size >> 8) & 0xFF; size_b0 = data_size & 0xFF
        packet_values = (op_code, 0x00, command_id, offset_b2, offset_b1, offset_b0, size_b2, size_b1, size_b0, 0x00, 0x00, 0x00)
        return struct.pack('!BBBBBBBBBBBB', *packet_values)
    except: return None

# --- 基板のサーバー機能 ---
# (ホストアプリからの状態遷移指令を受信するために別スレッドで動作)
command_received = threading.Event()

def board_server():
    print("[基板サーバー] 起動します。IP: 127.0.0.1, Port: 60202")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', BOARD_SERVER_PORT))
        s.listen()
        conn, addr = s.accept()
        with conn:
            print(f"[基板サーバー] ホストアプリ {addr} から接続あり。")
            cmd = conn.recv(12)
            data = conn.recv(4)
            data_val = struct.unpack('!I', data)[0]
            print(f"[基板サーバー] 状態遷移指令(->{hex(data_val)})を受信しました。")
            # ステータス(0)を返信
            conn.sendall(struct.pack('!I', 0))
            command_received.set() # メインスレッドに通知

# --- メイン処理 (基板のクライアント機能) ---
def send_report(phase_data):
    """ホストアプリに状態遷移報告を送信するクライアント関数"""
    phase_name = {0:'INITIALIZE', 8:'STANDBY', 0x2E:'RECONSTRUCT', 0x10:'IDLE'}.get(phase_data, 'UNKNOWN')
    print(f"\n[基板クライアント] ホストアプリ({HOST_APP_IP}:{HOST_APP_PORT})に接続します...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST_APP_IP, HOST_APP_PORT))
        print(f"[基板クライアント] 接続成功。状態遷移報告({phase_name})を送信します。")
        
        # コマンド、データ、ステータスをまとめて送信
        cmd_packet = create_command_packet(0x3B, 3, 0, 4)
        data_packet = struct.pack('!I', phase_data)
        status_packet = struct.pack('!I', 0)
        
        s.sendall(cmd_packet)
        s.sendall(data_packet)
        s.sendall(status_packet)
        print("[基板クライアント] 送信完了。接続を切断します。")

# --- 初期化シーケンス実行 ---
if __name__ == "__main__":
    # 1. 基板のサーバーを別スレッドで起動
    server_thread = threading.Thread(target=board_server)
    server_thread.start()
    
    print("===== 模擬制御基板 起動 (電源ON) =====")
    
    # 2. INITIALIZE -> STANDBY
    print("\n--- イニシャライズフェーズ実行 ---")
    time.sleep(2)
    send_report(0x00000000) # INITIALIZE報告
    print("...基板内部処理中...")
    time.sleep(3)
    send_report(0x00000008) # STANDBY報告
    
    # 3. ホストアプリからの指令を待つ
    print("\n--- ホストアプリからの指令待機中 ---")
    command_received.wait() # サーバーが指令を受信するまで待機
    
    # 4. RECONSTRUCT -> IDLE
    print("\n--- リコンストラクトフェーズ実行 ---")
    time.sleep(2)
    send_report(0x0000002E) # RECONSTRUCT報告
    print("...基板内部処理中...")
    time.sleep(4)
    send_report(0x00000010) # IDLE報告
    
    print("\n===== 模擬制御基板 処理完了 =====")
    server_thread.join()