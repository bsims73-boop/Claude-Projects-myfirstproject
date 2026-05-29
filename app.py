from datetime import date
import io
from pathlib import Path
import json as _json

from flask import Flask, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for

import config
from modules import db, exporter, programs, scanner

app = Flask(__name__)

_COUNTIES = _json.loads((config.BASE_DIR / "static" / "data" / "counties.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("receipts_page"))


@app.route("/receipts")
def receipts_page():
    return render_template("receipts.html")


@app.route("/summary")
def summary_page():
    return render_template("summary.html")


@app.route("/programs")
def programs_page():
    farm_types = programs.FARM_TYPES
    return render_template("programs.html", farm_types=farm_types)


@app.route("/api/counties/<path:state_name>")
def api_counties(state_name):
    counties = _COUNTIES.get(state_name)
    if counties is None:
        return jsonify({"error": "State not found"}), 404
    return jsonify(counties)


# ---------------------------------------------------------------------------
# Serve receipt images
# ---------------------------------------------------------------------------

@app.route("/receipts/image/<path:filename>")
def serve_receipt_image(filename):
    return send_from_directory(str(config.RECEIPTS_FOLDER), filename)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/scan", methods=["POST"])
def api_scan():
    result = scanner.scan_folder()
    return jsonify(result)


@app.route("/api/receipts")
def api_receipts():
    rows = db.get_all_receipts()
    receipts = []
    total_spend = 0.0
    for r in rows:
        receipts.append({
            "id": r["id"],
            "receipt_date": r["receipt_date"],
            "company_name": r["company_name"],
            "total_amount": r["total_amount"],
            "filename": r["filename"],
            "scan_status": r["scan_status"],
            "scan_error": r["scan_error"],
        })
        if r["total_amount"]:
            total_spend += r["total_amount"]

    last_scan = db.get_last_scan()
    return jsonify({
        "receipts": receipts,
        "total_count": len(receipts),
        "total_spend": round(total_spend, 2),
        "last_scan": last_scan["run_at"] if last_scan else None,
    })


@app.route("/api/receipts/<int:receipt_id>/items")
def api_line_items(receipt_id):
    items = db.get_line_items(receipt_id)
    return jsonify([dict(i) for i in items])


@app.route("/api/summary")
def api_summary():
    rows = db.get_monthly_summary()
    labels = []
    totals = []
    counts = []
    for r in rows:
        month_name = date(int(r["year"]), int(r["month"]), 1).strftime("%b %Y")
        labels.append(month_name)
        totals.append(round(r["total_spend"] or 0, 2))
        counts.append(r["receipt_count"])

    labels.reverse()
    totals.reverse()
    counts.reverse()

    return jsonify({"labels": labels, "totals": totals, "counts": counts})


@app.route("/api/programs", methods=["POST"])
def api_programs():
    body = request.get_json(force=True)
    state = body.get("state", "").strip()
    farm_type = body.get("farm_type", "").strip()
    if not state or not farm_type:
        return jsonify({"error": "state and farm_type are required"}), 400
    county = body.get("county", "").strip()
    if county and county not in _COUNTIES.get(state, []):
        county = ""
    try:
        page = int(body.get("page", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "page must be an integer"}), 400
    result = programs.research_farm_programs(state, farm_type, county, page)
    return jsonify(result)


@app.route("/api/export")
def api_export():
    xlsx_bytes = exporter.generate_excel()
    today = date.today().strftime("%Y-%m-%d")
    return send_file(
        io.BytesIO(xlsx_bytes),
        download_name=f"farm_receipts_{today}.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@app.errorhandler(Exception)
def handle_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": str(e)}), 500
    return render_template("error.html", error=str(e)), 500


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.init_db()
    config.RECEIPTS_FOLDER.mkdir(exist_ok=True)
    print("\n Farm Receipt Manager is running!")
    print(" Open your browser to: http://localhost:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
