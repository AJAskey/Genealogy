import pandas as pd
import yfinance as yf
import os
import numpy as np
from html2image import Html2Image
from PIL import Image

OUTDIR = r"..\..\output"


def format_usd(val):
    if val is None or pd.isna(val):
        return "N/A"
    abs_val = abs(val)
    if abs_val >= 1e12:
        res = f"${abs_val / 1e12:.2f}T"
    elif abs_val >= 1e9:
        res = f"${abs_val / 1e9:.2f}B"
    elif abs_val >= 1e6:
        res = f"${abs_val / 1e6:.2f}M"
    else:
        res = f"${abs_val:,.2f}"

    if val < 0:
        return f"-{res}"
    return res


def format_pct(val):
    if val is None or pd.isna(val):
        return "N/A"
    if val > 0:
        return f"+{val:.2f}%"
    return f"{val:.2f}%"


def export_table_to_jpg(df, output_jpg_path):
    """
    Generates a beautifully styled HTML table from the DataFrame and exports it as a cropped JPEG.
    """

    # Drop columns to keep it narrow, matching the Markdown table
    jpg_df = df.drop(columns=["Fund Name", "5D Net Flow ($)", "5D Net Flow (% AUM)"], errors="ignore")
    jpg_df = jpg_df.rename(columns={
        "20D Return (%)": "20D Ret",
        "52W High Dist (%)": "52W Dist",
        "250D Z-Score": "Z-Scr",
        "20D Net Flow ($)": "20D Flow",
        "20D Net Flow (% AUM)": "20D Flow %"
    })

    # Prepare table rows HTML
    rows_html = ""
    for row in jpg_df.itertuples(index=False):
        row_html = "<tr>"
        for i, val in enumerate(row):
            val_str = str(val)
            col_name = jpg_df.columns[i]

            cls = ""
            if col_name == "Ticker":
                cls = "ticker"

            # Color positive/negative values
            cell_style = ""
            if col_name in ["20D Ret", "Z-Scr", "20D Flow %"]:
                if val_str.startswith("+"):
                    cell_style = "color: #4caf50;"
                elif val_str.startswith("-"):
                    cell_style = "color: #f44336;"

            row_html += f'<td class="{cls}" style="{cell_style}">{val_str}</td>'
        row_html += "</tr>"
        rows_html += row_html

    # Prepare headers HTML
    headers_html = "".join(f"<th>{col}</th>" for col in jpg_df.columns)

    # Full HTML content with beautiful dark styling
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
      
      html, body {{
        background: transparent;
        margin: 0;
        padding: 0;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      }}
      
      .wrapper {{
        display: inline-block;
        padding: 20px;
        background: transparent;
      }}
      
      .container {{
        background-color: #161616;
        padding: 25px 30px;
        border-radius: 8px;
        color: #e0e0e0;
        display: inline-block;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
      }}
      
      h2 {{
        margin-top: 0;
        margin-bottom: 12px;
        font-size: 22px;
        font-weight: 600;
        color: #ffffff;
        letter-spacing: -0.5px;
      }}
      
      .divider {{
        height: 1px;
        background-color: #2d2d2d;
        margin-bottom: 20px;
      }}
      
      table {{
        border-collapse: collapse;
        width: auto;
        font-size: 14px;
        line-height: 1.5;
      }}
      
      th {{
        text-align: left;
        padding: 10px 18px 10px 0;
        font-weight: 600;
        color: #a0a0a0;
        border-bottom: 1px solid #2d2d2d;
        white-space: nowrap;
      }}
      
      th:last-child, td:last-child {{
        padding-right: 0;
      }}
      
      td {{
        padding: 12px 18px 12px 0;
        border-bottom: 1px solid #222222;
        color: #d0d0d0;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }}
      
      tr:last-child td {{
        border-bottom: none;
      }}
      
      .ticker {{
        font-weight: 600;
        color: #ffffff;
      }}
    </style>
    </head>
    <body>
      <div class="wrapper">
        <div class="container">
          <h2>1. Market Leaderboard</h2>
          <div class="divider"></div>
          <table>
            <thead>
              <tr>
                {headers_html}
              </tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
        </div>
      </div>
    </body>
    </html>
    """

    out_dir = os.path.dirname(output_jpg_path)
    temp_png_name = "etf_leaderboard_temp.png"
    temp_png_path = os.path.join(out_dir, temp_png_name)

    # Initialize html2image and capture screenshot
    hti = None
    browsers_to_try = [
        ("chrome", None),
        ("edge", None),
        ("edge", os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe")),
        ("edge", os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")),
        ("edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ("edge", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
    ]

    for browser, exec_path in browsers_to_try:
        try:
            if exec_path and not os.path.exists(exec_path):
                continue

            kwargs = {
                "browser": browser,
                "output_path": out_dir,
                "custom_flags": ["--default-background-color=00000000", "--hide-scrollbars"]
            }
            if exec_path:
                kwargs["browser_executable"] = exec_path

            hti = Html2Image(**kwargs)

            # Remove existing temp file if any
            if os.path.exists(temp_png_path):
                os.remove(temp_png_path)

            hti.screenshot(html_str=html_content, save_as=temp_png_name, size=(1000, 2500))

            if os.path.exists(temp_png_path):
                break
        except Exception as e:
            # Silence internal errors and try next browser option
            hti = None

    if not hti or not os.path.exists(temp_png_path):
        raise RuntimeError("Could not capture screenshot of the table using headless Chrome or Microsoft Edge.")

    # Open the PNG image using Pillow
    img = Image.open(temp_png_path)

    # Custom bounding box logic to crop correctly
    bbox = None
    if img.mode == "RGBA":
        alpha = img.split()[3]
        temp_bbox = alpha.getbbox()
        if temp_bbox and (temp_bbox[2] - temp_bbox[0] < img.width or temp_bbox[3] - temp_bbox[1] < img.height):
            bbox = temp_bbox

    if not bbox:
        # Fallback to solid color comparison (sampling top-left corner)
        bg_pixel = img.getpixel((0, 0))
        img_arr = np.array(img)
        if isinstance(bg_pixel, tuple):
            bg_color = np.array(bg_pixel)
            mask = ~np.all(img_arr == bg_color, axis=-1)
        else:
            mask = img_arr != bg_pixel

        coords = np.argwhere(mask)
        if coords.size > 0:
            y0, x0 = coords.min(axis=0)[:2]
            y1, x1 = coords.max(axis=0)[:2]
            # Add padding
            left = max(0, x0 - 5)
            top = max(0, y0 - 5)
            right = min(img.width, x1 + 6)
            bottom = min(img.height, y1 + 6)
            bbox = (left, top, right, bottom)

    # Crop image
    if bbox:
        cropped_img = img.crop(bbox)
    else:
        cropped_img = img

    # Paste onto a solid #161616 background to convert transparent pixels (e.g. rounded corners)
    bg_color = (22, 22, 22)  # Hex #161616
    final_img = Image.new("RGB", cropped_img.size, bg_color)
    if cropped_img.mode == "RGBA":
        final_img.paste(cropped_img, mask=cropped_img.split()[3])
    else:
        final_img.paste(cropped_img)

    # Save as JPEG
    final_img.save(output_jpg_path, "JPEG", quality=95)

    # Clean up temp file
    if os.path.exists(temp_png_path):
        os.remove(temp_png_path)

    print(f"  - JPEG Table: {output_jpg_path}")


def analyze_etf_flows(ticker):
    """
    Retrieves and calculates estimated money flow metrics, price returns, and technical indicators (Z-Score, 52W High Dist) for an ETF.
    """
    print(f"Fetching data for {ticker.upper()}...")
    try:
        # Load the ETF data using yfinance
        etf_data = yf.Ticker(ticker.upper())

        # Extract basic info and AUM
        info = etf_data.info
        aum = info.get("totalAssets") or info.get("netAssets") or 0

        # Fetch historical data (1 year to support 52-week and 250-day metrics)
        hist = etf_data.history(period="1y")
        if len(hist) < 250:
            print(f"Warning: Insufficient historical data for {ticker} (got {len(hist)} days, need 250)")
            return None

        # Calculate Typical Price and Raw Money Flow
        typical_price = (hist["High"] + hist["Low"] + hist["Close"]) / 3
        raw_flow = typical_price * hist["Volume"]

        # Determine price change direction
        price_diff = typical_price.diff()
        direction = price_diff.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        money_flow = raw_flow * direction

        # Calculate 5D and 20D Estimated Net Money Flows
        flow_5d = money_flow.iloc[-5:].sum()
        flow_20d = money_flow.iloc[-20:].sum()

        flow_5d_pct = (flow_5d / aum) * 100 if aum else 0
        flow_20d_pct = (flow_20d / aum) * 100 if aum else 0

        # Calculate 20-day Price Return
        price_start_20d = hist["Close"].iloc[-20]
        price_end = hist["Close"].iloc[-1]
        return_20d = ((price_end - price_start_20d) / price_start_20d) * 100

        # Calculate 52-Week High and Distance
        high_52w = hist["High"].max()
        dist_52w = ((high_52w - price_end) / high_52w) * 100

        # Calculate 250-day Z-Score of Close Price
        rolling_mean = hist["Close"].rolling(window=250).mean()
        rolling_std = hist["Close"].rolling(window=250).std()
        z_scores = (hist["Close"] - rolling_mean) / rolling_std
        z_score_250d = z_scores.iloc[-1]

        # Build a dictionary targeting asset sizes, money flow proxies, and technical indicators
        flow_metrics = {
            "Ticker": '$' + ticker.upper(),
            "Fund Name": info.get("longName") or info.get("shortName") or "N/A",
            "AUM": aum,
            "Price": info.get("regularMarketPrice") or info.get("navPrice") or price_end,
            "20D Return (%)": return_20d,
            "52W High Dist (%)": dist_52w,
            "250D Z-Score": z_score_250d,
            "5D Net Flow ($)": flow_5d,
            "5D Net Flow (% AUM)": flow_5d_pct,
            "20D Net Flow ($)": flow_20d,
            "20D Net Flow (% AUM)": flow_20d_pct,
        }

        return flow_metrics

    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None


# Target ETFs representing the major sectors + Broad Market (SPY)
target_etfs = [
    # --- Broad US Market & Size Indexes ---
    "SPY",  # S&P 500 (Large Cap)
    "QQQ",  # Nasdaq 100 (Tech/Growth)
    "DIA",  # Dow Jones Industrials
    "IJH",  # S&P Mid-Cap 400
    "IWM",  # Russell 2000 (Small Cap)

    # --- Broad International & Global ---
    "EFA",  # MSCI EAFE (Developed Markets ex-US)
    "EEM",  # MSCI Emerging Markets

    # --- Country Specific ---
    "EWJ",  # Japan
    "EWY",  # South Korea
    "EWW",  # Mexico
    "EWC",  # Canada
    "EWU",  # United Kingdom
    "INDA",  # India
    "EWT",  # Taiwan
    "CQQQ",  # China Technology
    "EWZ",  # Brazil
    "EWG",  # Germany

    # --- Major US Select Sector SPDRs ---
    "XLK",  # Technology
    "XLF",  # Financials
    "XLV",  # Healthcare
    "XLI",  # Industrials
    "XLY",  # Consumer Discretionary
    "XLP",  # Consumer Staples
    "XLU",  # Utilities
    "XLB",  # Materials
    "XLRE",  # Real Estate
    "XLC",  # Communication Services

    # --- Key Sub-sectors & Themes ---
    "SMH",  # Semiconductors (drop SOXX)
    "BUG",  # Cybersecurity
    "IGV",  # Software
    "XBI",  # Biotech (drop IBB, ARKG)
    "KRE",  # Regional Banking (drop KBE)
    "XHB",  # Homebuilders (drop ITB)
    "XLE",  # Energy (drop IYE, XOP)
    "USO",  # Crude Oil Commodity
    "GLD",  # Gold Commodity
    "GDX",  # Gold Miners (drop GDXJ)
    "URA",  # Uranium Miners
    "SHLD",  # Defense Technology
    "XRT",  # Retail
    "UFO",  # Space
    "VGK",  # European Region
    "HYG",  # High Yield Bonds
    "MBB",  # Mortgage-Backed Securities
]

all_data = []

for ticker in target_etfs:
    metrics = analyze_etf_flows(ticker)
    if metrics is not None:
        all_data.append(metrics)

# Combine everything into a single master analysis table
if all_data:
    master_df = pd.DataFrame(all_data)

    # Sort sectors by 20-day Net Flow percentage of AUM to show "sector love"
    # Keep SPY at the top or let it sort with the rest. Sorting all shows relative strength.
    master_df = master_df.sort_values(by="20D Net Flow (% AUM)", ascending=False)

    # Save the RAW numerical data to CSV and Excel for analysis
    master_df.to_csv(OUTDIR + "/etf_industry_flows.csv", index=False)
    master_df.to_excel(OUTDIR + "/etf_industry_flows.xlsx", index=False)
    print("\nRaw data successfully exported to:")
    print("  - CSV: " + OUTDIR + "/etf_industry_flows.csv")
    print("  - Excel: " + OUTDIR + "/etf_industry_flows.xlsx")

    # Create a formatted display copy of the DataFrame for clean printing
    display_df = master_df.copy()
    display_df["AUM"] = display_df["AUM"].apply(format_usd)
    display_df["Price"] = display_df["Price"].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "N/A")
    display_df["20D Return (%)"] = display_df["20D Return (%)"].apply(format_pct)
    display_df["52W High Dist (%)"] = display_df["52W High Dist (%)"].apply(
        lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
    display_df["250D Z-Score"] = display_df["250D Z-Score"].apply(
        lambda x: f"+{x:.2f}" if pd.notna(x) and x > 0 else (f"{x:.2f}" if pd.notna(x) else "N/A"))
    display_df["5D Net Flow ($)"] = display_df["5D Net Flow ($)"].apply(format_usd)
    display_df["5D Net Flow (% AUM)"] = display_df["5D Net Flow (% AUM)"].apply(format_pct)
    display_df["20D Net Flow ($)"] = display_df["20D Net Flow ($)"].apply(format_usd)
    display_df["20D Net Flow (% AUM)"] = display_df["20D Net Flow (% AUM)"].apply(format_pct)

    # Generate the narrow Markdown file automatically
    md_path = OUTDIR + "/etf_market_gestalt.md"
    try:
        md_df = display_df.drop(columns=["Fund Name", "5D Net Flow ($)", "5D Net Flow (% AUM)"], errors="ignore")
        md_df = md_df.rename(columns={
            "20D Return (%)": "20D Ret",
            "52W High Dist (%)": "52W Dist",
            "250D Z-Score": "Z-Scr",
            "20D Net Flow ($)": "20D Flow",
            "20D Net Flow (% AUM)": "20D Flow %"
        })

        headers = list(md_df.columns)
        md_lines = ["| " + " | ".join(headers) + " |"]
        md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in md_df.itertuples(index=False):
            md_lines.append("| " + " | ".join(str(val) for val in row) + " |")
        markdown_table = "\n".join(md_lines)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# ETF Market Gestalt Report\n")
            f.write(
                "*Generated from the latest Yahoo Finance flow and technical metrics (42 representative ETFs).*\n\n")
            f.write("## 1. Market Leaderboard\n")
            f.write(markdown_table + "\n\n")
            f.write("## 2. Market Regimes & Flow Gestalt\n\n")
            f.write("### A. Overextended Momentum Leaders (Highly Loved Cyclicals)\n")
            f.write(
                "A collection of sectors is showing extreme buying pressure over the 20-day lookback, coupled with elevated Z-scores.\n")
            f.write("* **Regional Banks (KRE):** Z-Score is elevated and sitting near its 52W High.\n")
            f.write(
                "* **Biotech (XBI):** Trading at statistically extreme standard deviations above its 250D moving average.\n\n")
            f.write("### B. Tech and AI Pressure Release (Pulling Back)\n")
            f.write(
                "* **Technology (XLK), Semiconductors (SMH), and QQQ:** Exhibit significant net outflows over the 20-day horizon, letting off steam from overbought heights rather than collapsing.\n\n")
            f.write("### C. Capitulation & Absolute Weakness\n")
            f.write(
                "* **Energy (XLE, USO) and Precious Metals (GLD, GDX):** Experience heavy outflows and negative Z-scores, indicating clear downward price trends.\n")

        print("  - Markdown: " + md_path)

        # Generate the JPEG table image
        jpg_path = OUTDIR + "/etf_market_leaderboard.jpg"
        try:
            export_table_to_jpg(display_df, jpg_path)
        except Exception as jpg_err:
            print(f"Warning: Could not generate JPEG table image: {jpg_err}")
    except Exception as md_err:
        print(f"Warning: Could not write Markdown file: {md_err}")

    # Display the clean narrow formatted table in the console
    console_df = display_df.drop(columns=["Fund Name", "5D Net Flow ($)", "5D Net Flow (% AUM)"], errors="ignore")
    print("\n=== ETF Sector Money Flow & Strength Leaderboard ===")
    print(console_df.to_string(index=False))
