
from flask import Flask, render_template, request, redirect, url_for, send_file
from datetime import datetime
from pytz import timezone
import sqlite3
import pandas as pd
from io import BytesIO

app = Flask(__name__)
db_path = "estacionamiento.db"
tz = timezone("America/Santiago")

def get_time_now():
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def init_db():
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patente TEXT,
            hora_entrada TEXT,
            hora_salida TEXT,
            monto INTEGER,
            medio_pago TEXT
        )
        """)

@app.route("/", methods=["GET", "POST"])
def index():
    mensaje = ""
    filtro_fecha = request.args.get("fecha", datetime.now(tz).strftime("%Y-%m-%d"))
    mostrar_monto = False
    minutos = 0
    monto = 0

    if request.method == "POST":
        patente = request.form["patente"].upper()
        now = get_time_now()
        medio_pago = request.form.get("medio_pago", "")

        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM registros WHERE patente = ? AND hora_salida IS NULL", (patente,))
            registro = cur.fetchone()

            if registro:
                # Es una salida
                hora_entrada = datetime.strptime(registro[2], "%Y-%m-%d %H:%M:%S")
                hora_salida = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
                minutos_original = int((hora_salida - hora_entrada).total_seconds() / 60)
                unidad = minutos_original % 10
                if unidad < 5:
                    minutos = minutos_original - unidad
                else:
                    minutos = minutos_original + (10 - unidad)
                monto = 500 if minutos <= 15 else 500 + (minutos - 15) * 24

                if medio_pago:
                    cur.execute("UPDATE registros SET hora_salida = ?, monto = ?, medio_pago = ? WHERE id = ?",
                                (now, monto, medio_pago, registro[0]))
                    return redirect(url_for('index', fecha=filtro_fecha))
                else:
                    mostrar_monto = True
            else:
                # Es un ingreso
                cur.execute("INSERT INTO registros (patente, hora_entrada) VALUES (?, ?)", (patente, now))
                return redirect(url_for('index', fecha=filtro_fecha))

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            WITH salidas AS (
                SELECT * FROM registros
                WHERE DATE(hora_entrada) = ? AND hora_salida IS NOT NULL
                ORDER BY hora_salida DESC
                LIMIT 1
            ),
            restantes AS (
                SELECT * FROM registros
                WHERE DATE(hora_entrada) = ? AND hora_salida IS NULL
            ),
            anteriores AS (
                SELECT * FROM registros
                WHERE DATE(hora_entrada) = ? AND hora_salida IS NOT NULL
                AND id NOT IN (SELECT id FROM salidas)
            )
            SELECT * FROM restantes
            UNION ALL
            SELECT * FROM salidas
            UNION ALL
            SELECT * FROM anteriores
        """, (filtro_fecha, filtro_fecha, filtro_fecha))
        registros = cur.fetchall()

        cur.execute("SELECT medio_pago, SUM(monto) FROM registros WHERE DATE(hora_entrada) = ? AND monto IS NOT NULL GROUP BY medio_pago", (filtro_fecha,))
        totales = {medio: total for medio, total in cur.fetchall()}
        total_general = sum(totales.values()) if totales else 0

    return render_template("index.html", registros=registros, mensaje=mensaje, fecha=filtro_fecha,
                           mostrar_monto=mostrar_monto, minutos=minutos, monto=monto,
                           totales=totales, total_general=total_general)

@app.route("/editar/<int:registro_id>", methods=["GET", "POST"])
def editar(registro_id):
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        if request.method == "POST":
            cur.execute("""
                UPDATE registros
                SET patente = ?, hora_entrada = ?, hora_salida = ?, monto = ?, medio_pago = ?
                WHERE id = ?
            """, (
                request.form["patente"],
                request.form["hora_entrada"],
                request.form["hora_salida"] or None,
                request.form["monto"] or None,
                request.form["medio_pago"] or None,
                registro_id
            ))
            return redirect("/")
        cur.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
        registro = cur.fetchone()
    return render_template("editar.html", registro=registro)

@app.route("/eliminar/<int:registro_id>")
def eliminar(registro_id):
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM registros WHERE id = ?", (registro_id,))
    return redirect(url_for('index'))

@app.route("/exportar")
def exportar():
    fecha = request.args.get("fecha")
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query("SELECT * FROM registros WHERE DATE(hora_entrada) = ?", conn, params=(fecha,))
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, download_name=f"registros_{fecha}.xlsx", as_attachment=True)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
