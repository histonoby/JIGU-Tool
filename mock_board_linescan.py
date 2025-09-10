import socket
import struct
import time
import threading

# --- 共通の関数と定数 ---
HOST_APP_IP = '127.0.0.1'
HOST_APP_PORT = 60201  # アプリのサーバーポート
BOARD_SERVER_PORT = 60202 # 基板自身のサーバーポート

def create_command_packet(op_code, command_id, offset, data_size):
    try:
        offset_b2 = (offset >> 16) & 0xFF; offset_b1 = (offset >> 8) & 0xFF; offset_b0 = offset & 0xFF
        size_b2 = (data_size >> 16) & 0xFF; size_b1 = (data_size >> 8) & 0xFF; size_b0 = data_size & 0xFF
        packet_values = (op_code, 0x00, command_id, offset_b2, offset_b1, offset_b0, size_b2, size_b1, size_b0, 0x00, 0x00, 0x00)
        return struct.pack('!BBBBBBBBBBBB', *packet_values)
    except: return None

def send_to_app(command_id, data_value):
    """ホストアプリにコマンドを送信するクライアント関数"""
    print(f"\n[基板クライアント] -> アプリ({HOST_APP_IP}:{HOST_APP_PORT})に接続します。")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST_APP_IP, HOST_APP_PORT))
        cmd_packet = create_command_packet(0x3B, command_id, 0, 4)
        data_packet = struct.pack('!I', data_value)
        status_packet = struct.pack('!I', 0)
        
        s.sendall(cmd_packet)
        s.sendall(data_packet)
        s.sendall(status_packet)
        print(f"[基板クライアント] ID:{hex(command_id)}, Data:{hex(data_value)} を送信完了。")

# --- メイン処理 (基板のサーバー) ---
if __name__ == "__main__":
    print("===== 模擬制御基板 (ラインスキャンモード) 起動 =====")
    print(f"[基板サーバー] IP: 127.0.0.1, Port: {BOARD_SERVER_PORT} で待機中...")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', BOARD_SERVER_PORT))
        s.listen()

        # 1 & 2. アプリからのスキャン開始コマンド2つを受信
        print("\n--- アプリからのスキャン開始コマンド待機中 ---")
        conn, addr = s.accept()
        with conn:
            # ▼▼▼【変更点】▼▼▼
            # コマンドとデータをまとめて受信
            cmd1 = conn.recv(12 + 4) 
            # status1 = conn.recv(4) # ← この不要な受信待機を削除
            print("[基板サーバー] 1つ目のコマンド(ID:0x14)を受信しました。")
            # 受信後、すぐにステータスを返信
            conn.sendall(struct.pack('!I', 0))
            # ▲▲▲【変更点】▲▲▲

        conn, addr = s.accept()
        with conn:
            # ▼▼▼【変更点】▼▼▼
            cmd2 = conn.recv(12 + 4)
            # status2 = conn.recv(4) # ← この不要な受信待機を削除
            print("[基板サーバー] 2つ目のコマンド(ID:0x01, Data:0x54)を受信しました。")
            # 受信後、すぐにステータスを返信
            conn.sendall(struct.pack('!I', 0))
            # ▲▲▲【変更点】▲▲▲

        # 3 & 4. 状態遷移報告とステージ移動依頼をアプリへ送信
        time.sleep(1)
        send_to_app(command_id=0x03, data_value=0x54) # Phase:ラインスキャン報告
        time.sleep(1)
        send_to_app(command_id=0x05, data_value=0x00) # ステージ助走位置移動依頼
        
        # 5. アプリからの助走位置移動完了コマンドを受信
        print("\n--- アプリからの助走位置移動完了(ID:0x09)コマンド待機中 ---")
        conn, addr = s.accept()
        with conn:
            # ▼▼▼【変更点】▼▼▼
            cmd3 = conn.recv(12 + 4)
            print("[基板サーバー] 助走位置移動完了コマンドを受信しました。")
            conn.sendall(struct.pack('!I', 0)) # すぐに返信
            # ▲▲▲【変更点】▲▲▲

        # 6. ステージ測定移動依頼をアプリへ送信
        time.sleep(2) # 基板の内部処理を模擬
        send_to_app(command_id=0x06, data_value=0x00) # ステージ測定移動依頼
        
        # 7. アプリからの測定移動完了コマンドを受信
        print("\n--- アプリからの測定移動完了(ID:0x0A)コマンド待機中 ---")
        conn, addr = s.accept()
        with conn:
            # ▼▼▼【変更点】▼▼▼
            cmd4 = conn.recv(12 + 4)
            print("[基板サーバー] 測定移動完了コマンドを受信しました。")
            conn.sendall(struct.pack('!I', 0)) # すぐに返信
            # ▲▲▲【変更点】▲▲▲

        # 8. Phase:アイドル報告をアプリへ送信
        time.sleep(2) # 基板の内部処理を模擬
        send_to_app(command_id=0x03, data_value=0x10)
        
        # 9. アプリからのデータ読み出しコマンドを受信
        print("\n--- アプリからのデータ読み出し(ID:0x54)コマンド待機中 ---")
        conn, addr = s.accept()
        with conn:
            read_cmd = conn.recv(12)
            print("[基板サーバー] データ読み出しコマンドを受信しました。")
            
            data_size = 43400
            dummy_data = bytes([i % 256 for i in range(data_size)])
            print(f"[基板サーバー] {data_size}バイトのダミーデータを送信します。")
            conn.sendall(dummy_data)
            
            conn.sendall(struct.pack('!I', 0))
            print("[基板サーバー] データ送信完了。")

    print("\n===== 模擬制御基板 (ラインスキャンモード) 処理完了 =====")