"""
Verify that chart XML was fixed correctly.
"""

import zipfile
from pathlib import Path
import sys


def verify_chart_xml(xlsx_path: Path):
    """Check whether chart XML in an xlsx file matches expectations."""
    print(f"\n{'='*60}")
    print(f"Checking: {xlsx_path}")
    print('='*60)
    
    try:
        with zipfile.ZipFile(xlsx_path, 'r') as zf:
            chart_files = [n for n in zf.namelist() if n.startswith('xl/charts/') and n.endswith('.xml')]
            
            if not chart_files:
                print("❌ No chart files found")
                return False
            
            all_ok = True
            for chart_name in chart_files:
                print(f"\n📊 {chart_name}:")
                content = zf.read(chart_name).decode('utf-8')
                
                if 'roundedCorners' in content:
                    if 'roundedCorners val="0"' in content or 'roundedCorners val=\'0\'' in content:
                        print("  ✅ roundedCorners = 0")
                    else:
                        print("  ❌ roundedCorners exists but is not 0")
                        all_ok = False
                else:
                    print("  ❌ roundedCorners is missing")
                    all_ok = False
                
                import re
                styles = re.findall(r'<(?:c:)?style[^>]*val="(\d+)"', content)
                if styles:
                    high_styles = [s for s in styles if int(s) > 10]
                    if high_styles:
                        print(f"  ❌ Found high style numbers: {high_styles}")
                        all_ok = False
                    else:
                        print(f"  ✅ Style numbers look normal: {styles}")
                else:
                    print("  ⚠️  style tag not found")
                
                if '<legend' in content.lower():
                    if 'overlay val="0"' in content or 'overlay val=\'0\'' in content:
                        print("  ✅ legend.overlay = 0")
                    else:
                        print("  ❌ legend.overlay is not 0 or is missing")
                        all_ok = False
                    
                    if 'legendPos val="r"' in content or 'legendPos val=\'r\'' in content:
                        print("  ✅ legend.position = r")
                    else:
                        print("  ⚠️  legend.position is not r")
                
                shapes = re.findall(r'<(?:c:)?shape[^>]*val="([^"]+)"', content)
                if shapes:
                    if any(s in ['cone', 'coneToMax', 'pyramid', 'pyramidToMax', 'cylinder'] for s in shapes):
                        print(f"  ❌ Found modern shapes: {shapes}")
                        all_ok = False
                    else:
                        print(f"  ✅ Shapes look normal: {shapes}")
                
                print(f"\n  XML snippet:")
                print(f"  {content[:500]}...")
            
            return all_ok
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_chart_fix.py <xlsx_path> [<xlsx_path2> ...]")
        sys.exit(1)
    
    for path in sys.argv[1:]:
        verify_chart_xml(Path(path))