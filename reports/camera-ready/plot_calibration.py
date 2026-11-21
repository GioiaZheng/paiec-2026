"""Vector reliability plots from the verified aggregate results (ReportLab)."""
import json
from pathlib import Path
from reportlab.graphics import renderPDF
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String, Line, Group, STATE_DEFAULTS
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
import reportlab

HERE = Path(__file__).resolve().parent
font_dir = Path(reportlab.__file__).resolve().parent/'fonts'
pdfmetrics.registerFont(TTFont('PlotSans', str(font_dir/'Vera.ttf')))
pdfmetrics.registerFont(TTFont('PlotBold', str(font_dir/'VeraBd.ttf')))
STATE_DEFAULTS['fontName'] = 'PlotSans'
result = json.loads((HERE/'analysis/results.json').read_text())
d = Drawing(440, 192)
palette = [colors.HexColor('#1d5d8f'), colors.HexColor('#b04836')]
for x, label, color in [(70, 'Empirical mean', palette[0]), (230, 'Beta(1,1)', palette[1])]:
    d.add(Line(x, 182, x+15, 182, strokeColor=color, strokeWidth=1.4))
    d.add(String(x+20, 179, label, fontName='PlotSans', fontSize=9))
for i, budget in enumerate(['1','3']):
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 43+i*220, 30, 170, 122
    lp.data = [[(0,0),(1,1)]] + [[(p['p'], p['observed']) for p in result['calibration']['all'][budget][m]['points']]
                                        for m in ['empirical_mean','beta_1_1']]
    for axis in [lp.xValueAxis, lp.yValueAxis]:
        axis.valueMin, axis.valueMax, axis.valueSteps = 0, 1, [0,.25,.5,.75,1]
        axis.labels.fontName, axis.labels.fontSize = 'PlotSans', 7.5
        axis.strokeWidth = .5
    lp.lines[0].strokeColor = colors.HexColor('#999999')
    lp.lines[0].strokeDashArray = [3,3]
    lp.lines[0].strokeWidth = .7
    for j, marker in enumerate(['FilledCircle','FilledSquare']):
        line = lp.lines[j+1]
        line.strokeColor, line.strokeWidth = palette[j], 1.25
        line.symbol = makeMarker(marker)
        line.symbol.size = 4
        line.symbol.fillColor = palette[j]
        line.symbol.strokeColor = palette[j]
    d.add(lp)
    d.add(String(lp.x+85, 162, 'Budget '+budget, textAnchor='middle', fontName='PlotBold', fontSize=10))
    d.add(String(lp.x+85, 6, 'Predicted probability', textAnchor='middle', fontName='PlotSans', fontSize=8))
    ylabel = Group(String(0, 0, 'Weighted outcome rate', textAnchor='middle', fontName='PlotSans', fontSize=8))
    ylabel.translate(lp.x-31, lp.y+61)
    ylabel.rotate(90)
    d.add(ylabel)
(HERE/'figures').mkdir(exist_ok=True)
canvas = Canvas(str(HERE/'figures/reliability.pdf'), pagesize=(440,192), initialFontName='PlotSans', invariant=1)
renderPDF.draw(d, canvas, 0, 0)
canvas.showPage()
canvas.save()
