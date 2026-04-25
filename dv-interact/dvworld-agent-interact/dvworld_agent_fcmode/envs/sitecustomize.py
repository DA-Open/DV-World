# Auto-generated to register SimHei for matplotlib
from pathlib import Path
from matplotlib import font_manager, rcParams
fp = Path(r"./SimHei.ttf")
if fp.exists():
    font_manager.fontManager.addfont(str(fp))
    name = font_manager.FontProperties(fname=fp).get_name()
    rcParams['font.sans-serif'] = [name, 'SimHei']
    rcParams['font.family'] = 'sans-serif'
    rcParams['axes.unicode_minus'] = False
