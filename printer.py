import socket
from config import PRINTER_IP, PRINTER_PORT

def send_escpos_raw(commands: bytes):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((PRINTER_IP, PRINTER_PORT))
    s.sendall(commands)
    s.close()

def print_repair_token(data, job_id):
    try:
        raw = bytearray()
        raw += b"\x1b\x40\x1b\x61\x01\x1d\x21\x11\x1b\x45\x01"
        raw += b"SAMEER MOBILE\n\x1d\x21\x00\x1b\x45\x00"
        raw += b"Mobile Repair & Solutions\n--------------------------------\n\x1d\x21\x01\x1b\x45\x01"
        raw += f"TOKEN: #{job_id}\n".encode("utf-8")
        raw += b"\x1d\x21\x00\x1b\x45\x00--------------------------------\n\x1b\x61\x00"
        raw += f"Date:     {data['date']}\nCustomer: {data['name']}\nModel:    {data['model']}\nFault:    {data['fault']}\n".encode("utf-8")

        lock = data.get("lock_code", "None")
        if lock and lock != "None":
            raw += f"Lock/PIN: {lock}\n".encode("utf-8")
        if data.get("imei") and data.get("imei") != "N/A":
            raw += f"IMEI:     {data['imei']}\n".encode("utf-8")

        raw += f"Est. Amt: Rs. {data['charged']:.2f}\n--------------------------------\n\x1b\x61\x01"
        raw += b"Bring token for device pickup\n*** Thank You ***\n\n\n\n\x1d\x56\x41\x10"
        send_escpos_raw(bytes(raw))
        return True, "Printed"
    except Exception as e:
        return False, str(e)

def print_eod_report(today_str, total_jobs, total_cost, total_charged, total_profit):
    try:
        raw = bytearray()
        raw += b"\x1b\x40\x1b\x61\x01\x1d\x21\x11\x1b\x45\x01DAILY CLOSING REPORT\n\x1d\x21\x00\x1b\x45\x00"
        raw += f"Date: {today_str}\n--------------------------------\n\x1b\x61\x00".encode("utf-8")
        raw += f"Total Jobs:    {total_jobs}\nTotal Cost:    Rs. {total_cost:.2f}\nTotal Revenue: Rs. {total_charged:.2f}\n--------------------------------\n\x1b\x45\x01".encode("utf-8")
        raw += f"NET PROFIT:    Rs. {total_profit:.2f}\n\x1b\x45\x00--------------------------------\n\n\n\n\x1d\x56\x41\x10".encode("utf-8")
        send_escpos_raw(bytes(raw))
        return True
    except Exception:
        return False