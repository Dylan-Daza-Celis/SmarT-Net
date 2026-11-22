"""Sanitized, deterministic CSV/JSON/PDF renderers for stored report snapshots."""
import csv
import io
import json
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle


def csv_cell(value):
    # Spreadsheet programs can execute formulas even in correctly quoted CSV cells.
    if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n'))):
        return "'"+value
    return value


def csv_bytes(payload, sha):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    def write(row): writer.writerow([csv_cell(v) for v in row])
    write(['record', 'key', 'value', 'unit', 'status', 'reason', 'details_json'])
    write(['metadata', 'snapshot', payload['id'], '', '', '', json.dumps({
        'generated_at': payload['generated_at'], 'content_sha256': sha, 'filters': payload['dashboard']['filters'],
        'methodology': payload['dashboard']['methodology'], 'limitations': payload['dashboard']['limitations'],
        'provenance': payload['dashboard']['provenance']}, ensure_ascii=True, sort_keys=True)])
    dash = payload['dashboard']
    for key, value in dash['totals'].items(): write(['indicator', key, value, 'count'])
    for key, values in dash['distributions'].items():
        for row in values: write(['distribution', key, row['count'], 'count', '', '', json.dumps(row, ensure_ascii=True)])
    for row in dash['trends']: write(['trend', row['date'], '', 'count', '', '', json.dumps(row, sort_keys=True)])
    for key, m in dash['response_metrics'].items():
        write(['metric', key, m['value'], m['unit'], m['status'], m['reason'], json.dumps({'valid': m['valid'], 'total': m['total']})])
    for row in payload['incidents']:
        write(['incident', row['id'], row['score'], 'score/100', row['status'], '', json.dumps(row, sort_keys=True, ensure_ascii=True)])
    return output.getvalue().encode('utf-8-sig')


def pdf_bytes(payload, sha):
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    styles['Normal'].fontSize = 9
    styles['Normal'].leading = 12
    def p(text): return Paragraph(escape(str(text)), styles['Normal'])
    story = [Paragraph('SmartIR-Net · Reporte analítico', styles['Title']),
        p('Snapshot: '+payload['id']), p('Generado UTC: '+payload['generated_at']),
        p('SHA-256 del payload JSON canónico: '+sha), Spacer(1, 12)]
    dash = payload['dashboard']
    story += [Paragraph('Periodo y filtros', styles['Heading2'])]
    for key, value in dash['filters'].items(): story.append(p(f'{key}: {value if value is not None else "Todos"}'))
    t = dash['totals']
    story += [Paragraph('Resumen ejecutivo', styles['Heading2']),
        p(f"La cohorte contiene {t['incidents']} incidentes y {t['events']} eventos deduplicados. "
          f"Abiertos: {t['open']}; resueltos: {t['resolved']}; cerrados: {t['closed']}. "
          f"Sin responsable: {t['unassigned']}; pendientes de revisión: {t['needs_review']}; críticos abiertos: {t['critical_open']}.")]
    def table(rows, widths=None):
        result = LongTable([[p(v) for v in row] for row in rows], colWidths=widths, repeatRows=1, hAlign='LEFT')
        result.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#dbe7f5')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), .25, colors.lightgrey),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
        return result
    for key, rows in dash['distributions'].items():
        story += [Paragraph('Distribución: '+key, styles['Heading2']), table([['Categoría', 'Cantidad']]+[[r['name'], r['count']] for r in rows], [540, 160])]
    story += [Paragraph('Métricas de respuesta', styles['Heading2']), table([['Indicador', 'Segundos', 'Cobertura', 'Limitación']]+[
        [key, m['value'] if m['value'] is not None else 'No calculable', f"{m['valid']}/{m['total']}", m['reason'] or 'Cohorte completa']
        for key, m in dash['response_metrics'].items()], [160, 100, 80, 360])]
    story += [Paragraph('Resultados por incidente', styles['Heading2']), table([['UUID', 'Tipo', 'Prioridad / score', 'Estado', 'Asignado', 'Eventos']]+[
        [r['id'], r['event_type'], f"{r['priority']} / {r['score']}", r['status'], 'Sí' if r['assigned'] else 'No', r['event_count']]
        for r in payload['incidents']], [215, 140, 100, 100, 65, 80])]
    story += [Paragraph('Tendencias diarias UTC', styles['Heading2']), table([['Fecha', 'Eventos', 'Incidentes', 'Críticos']]+[
        [r['date'], r['events'], r['incidents'], r['critical']] for r in dash['trends']], [220, 160, 160, 160])]
    story += [Paragraph('Metodología y procedencia', styles['Heading2'])]
    for key, value in dash['methodology'].items(): story.append(p(f'{key}: {value}'))
    story.append(p(dash['provenance']['reason']))
    story.append(Paragraph('Limitaciones', styles['Heading2']))
    story += [p(text) for text in dash['limitations']]
    def footer(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.drawString(32, 19, 'SmartIR-Net · '+payload['id']+' · Página '+str(doc.page))
    SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=32, leftMargin=32,
        topMargin=30, bottomMargin=34, title='SmartIR-Net - Reporte analítico', author='SmartIR-Net', invariant=1).build(
        story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
