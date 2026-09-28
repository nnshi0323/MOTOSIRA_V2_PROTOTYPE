"""
MOTOSIRA — PDF diagnosis report generator
Produces a single-page technical report per diagnosis (thesis scope:
'exportable technical report feature (PDF/CSV)').
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
import time
from reportlab.lib.pagesizes import letter          # type: ignore
from reportlab.lib.units import inch                # type: ignore
from reportlab.lib import colors                     # type: ignore
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,   # type: ignore
                                 Paragraph, Spacer)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle    # type: ignore
import config

SEVERITY_COLOR = {
    0: colors.HexColor("#2E7D32"),
    1: colors.HexColor("#B8860B"),
    2: colors.HexColor("#C1590A"),
    3: colors.HexColor("#C62828"),
}


def build_report_pdf(record: dict) -> bytes:
    """
    record keys: id, timestamp (epoch), model, classification, confidence,
    severity, action, signal_quality, snr_db, peak_dbfs, rpm
    Returns raw PDF bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                             topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                             leftMargin=0.75 * inch, rightMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('MTitle', parent=styles['Title'], fontSize=20,
                                  textColor=colors.HexColor("#1a1200"))
    sub_style = ParagraphStyle('MSub', parent=styles['Normal'], fontSize=10,
                                textColor=colors.HexColor("#666"))
    section_style = ParagraphStyle('MSection', parent=styles['Heading2'], fontSize=12,
                                    spaceBefore=14, textColor=colors.HexColor("#1a1200"))

    elems = []
    elems.append(Paragraph("MOTOSIRA — Diagnosis Report", title_style))
    elems.append(Paragraph(
        "Motorcycle Sound-based Identification &amp; Reporting Assistant", sub_style))
    elems.append(Spacer(1, 14))

    dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.get('timestamp', time.time())))
    sev_level = record.get('severity', 0)
    sev_color = SEVERITY_COLOR.get(sev_level, colors.black)

    header_data = [
        ["Report ID", f"#{record.get('id', '—')}"],
        ["Date / Time", dt],
        ["Motorcycle Model", record.get('model', config.DEFAULT_MODEL)],
    ]
    header_table = Table(header_data, colWidths=[1.8 * inch, 4.5 * inch])
    header_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#666")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#ddd")),
    ]))
    elems.append(header_table)

    elems.append(Paragraph("Diagnosis Result", section_style))
    label = record.get('classification', 'unknown').replace('_', ' ').upper()
    result_data = [
        ["Detected Condition", label],
        ["Confidence", f"{record.get('confidence', 0):.0%}"],
        ["Severity Level", f"{sev_level} / 3"],
        ["Recommended Action", record.get('action', '—')],
    ]
    result_table = Table(result_data, colWidths=[1.8 * inch, 4.5 * inch])
    result_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#666")),
        ('TEXTCOLOR', (1, 0), (1, 0), sev_color),
        ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (1, 0), (1, 0), 13),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#ddd")),
    ]))
    elems.append(result_table)

    elems.append(Paragraph("Capture Diagnostics", section_style))
    diag_data = [
        ["Input Quality", record.get('signal_quality') or "—"],
        ["Signal-to-Noise Ratio", f"{record.get('snr_db'):.1f} dB" if record.get('snr_db') is not None else "—"],
        ["Peak Level", f"{record.get('peak_dbfs'):.1f} dBFS" if record.get('peak_dbfs') is not None else "—"],
        ["Engine RPM", f"{record.get('rpm')} RPM" if record.get('rpm') else "Sensor not connected"],
        ["Processing Latency", f"{record.get('latency_ms')} ms" if record.get('latency_ms') is not None else "—"],
    ]
    diag_table = Table(diag_data, colWidths=[1.8 * inch, 4.5 * inch])
    diag_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#666")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    elems.append(diag_table)

    steps = record.get('steps') or []
    if steps:
        elems.append(Paragraph("Suggested Troubleshooting Steps", section_style))
        step_style = ParagraphStyle('Step', parent=styles['Normal'], fontSize=10,
                                     leftIndent=14, spaceAfter=5,
                                     textColor=colors.HexColor("#222"))
        for i, step in enumerate(steps, 1):
            elems.append(Paragraph(f"{i}. {step}", step_style))

    elems.append(Spacer(1, 24))
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8,
                                   textColor=colors.HexColor("#999"))
    elems.append(Paragraph(
        "Generated by MOTOSIRA — acoustic diagnosis only; does not interface with the "
        "motorcycle's electrical or ignition system. Confirm findings with a licensed "
        "mechanic before repair.", footer_style))

    doc.build(elems)
    return buf.getvalue()
