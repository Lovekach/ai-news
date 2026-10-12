"""Apply a prepared audit correction manifest, preserving old texts locally."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ainews.store import Store
from ainews.telegram import edit_message, read_token
from ainews.security import safe_error


def main():
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    token = read_token()
    store = Store(ROOT / ".state/news.sqlite3")
    receipt_path = Path(sys.argv[1]).with_suffix('.results.json')
    results = {}
    if receipt_path.exists():
        results = json.loads(receipt_path.read_text(encoding='utf-8'))
    try:
        for change in manifest:
            if change["kind"] == "digest":
                row = store.digest(change["slot"])
                current = row["text"] if row else None
            else:
                row = store.sent_item(change["url"])
                current = row["draft"] if row else None
            new = change["new_text"]
            if current == new:
                print(f"ALREADY SAVED message_id={change['message_id']}", flush=True)
                continue
            if row is None or current != change["old_text"] or row["telegram_message_id"] != change["message_id"]:
                raise RuntimeError(f"Local publication changed since audit: message_id={change['message_id']}")
            if not new or len(new.encode('utf-16-le')) // 2 > 4096:
                raise ValueError("Correction exceeds Telegram message limit")
            try:
                edit_message(token, int(config["channel_id"]), change["message_id"], new)
            except RuntimeError as exc:
                # A prior request may have succeeded before local saving.
                if "message is not modified" not in str(exc):
                    results[str(change['message_id'])] = {'state':'failed','reason':safe_error(exc)}
                    receipt_path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(f"FAILED message_id={change['message_id']}: {safe_error(exc)}",flush=True)
                    continue
            if change["kind"] == "digest":
                store.record_digest_correction(change["slot"], current, new)
            else:
                store.record_correction(change["url"], current, new)
            print(f"CORRECTED message_id={change['message_id']} chars={len(new)}", flush=True)
            results[str(change['message_id'])] = {'state':'corrected','chars':len(new)}
            receipt_path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            time.sleep(1)
    finally:
        store.close()


if __name__ == '__main__':
    main()
