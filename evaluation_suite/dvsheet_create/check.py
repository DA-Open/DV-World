"""
验证图表 XML 是否已正确修复。
"""

import zipfile
from pathlib import Path
import sys


def verify_chart_xml(xlsx_path: Path):
    """检查 xlsx 中的图表 XML 是否符合预期"""
    print(f"\n{'='*60}")
    print(f"检查: {xlsx_path}")
    print('='*60)
    
    try:
        with zipfile.ZipFile(xlsx_path, 'r') as zf:
            chart_files = [n for n in zf.namelist() if n.startswith('xl/charts/') and n.endswith('.xml')]
            
            if not chart_files:
                print("❌ 未找到图表文件")
                return False
            
            all_ok = True
            for chart_name in chart_files:
                print(f"\n📊 {chart_name}:")
                content = zf.read(chart_name).decode('utf-8')
                
                # 检查 roundedCorners
                if 'roundedCorners' in content:
                    if 'roundedCorners val="0"' in content or 'roundedCorners val=\'0\'' in content:
                        print("  ✅ roundedCorners = 0")
                    else:
                        print("  ❌ roundedCorners 存在但值不为 0")
                        all_ok = False
                else:
                    print("  ❌ 缺少 roundedCorners")
                    all_ok = False
                
                # 检查 style
                import re
                styles = re.findall(r'<(?:c:)?style[^>]*val="(\d+)"', content)
                if styles:
                    high_styles = [s for s in styles if int(s) > 10]
                    if high_styles:
                        print(f"  ❌ 发现高样式号: {high_styles}")
                        all_ok = False
                    else:
                        print(f"  ✅ 样式号正常: {styles}")
                else:
                    print("  ⚠️  未找到 style 标签")
                
                # 检查 legend
                if '<legend' in content.lower():
                    if 'overlay val="0"' in content or 'overlay val=\'0\'' in content:
                        print("  ✅ legend.overlay = 0")
                    else:
                        print("  ❌ legend.overlay 不为 0 或缺失")
                        all_ok = False
                    
                    if 'legendPos val="r"' in content or 'legendPos val=\'r\'' in content:
                        print("  ✅ legend.position = r")
                    else:
                        print("  ⚠️  legend.position 不为 r")
                
                # 检查 shape
                shapes = re.findall(r'<(?:c:)?shape[^>]*val="([^"]+)"', content)
                if shapes:
                    if any(s in ['cone', 'coneToMax', 'pyramid', 'pyramidToMax', 'cylinder'] for s in shapes):
                        print(f"  ❌ 发现现代形状: {shapes}")
                        all_ok = False
                    else:
                        print(f"  ✅ 形状正常: {shapes}")
                
                # 显示前 500 字符用于调试
                print(f"\n  XML 片段:")
                print(f"  {content[:500]}...")
            
            return all_ok
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python verify_chart_fix.py <xlsx文件路径> [<xlsx文件路径2> ...]")
        sys.exit(1)
    
    for path in sys.argv[1:]:
        verify_chart_xml(Path(path))