import concurrent.futures
import logging
import os
import threading
import time
import pandas as pd
from datetime import datetime, timedelta
import traceback


class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            encoding = getattr(stream, "encoding", None) or "utf-8"

            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                safe_msg = msg.encode(encoding, errors="replace").decode(encoding, errors="replace")
                stream.write(safe_msg + self.terminator)

            self.flush()
        except Exception:
            self.handleError(record)

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from openalgo import api, ta

from retrieve_nifty_symbols import get_nifty_constituents

# =========================
# LOGGING
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) or "."
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

LOG_FILE = os.path.join(OUTPUT_DIR, f"strategy_output_{datetime.now():%Y%m%d_%H%M%S}.log")
logger = logging.getLogger("strategy_output")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    console_handler = SafeStreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

logger.info("🔁 OpenAlgo Python Bot is running.")

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("OPENALGO_API_KEY")
HOST = os.getenv("HOST_SERVER") or os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

required_cols = ["open", "high", "low", "close", "volume"]
one_year_ago = pd.Timestamp(datetime.now() - timedelta(days=365))

OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"strategy_output_{datetime.now():%Y%m%d_%H%M%S}.xlsx")

# Column order in the output workbook: Symbol, then all concise columns first, then all detailed columns
COLUMNS = [
    "Symbol",
    "RSI5 Value",
    "MACD Value",
    "EMA Ribbon",
    "Stochastic Value",
    "Volume Value",
    "Candle % Change",
    "RSI5",
    "MACD",
    "Stochastic",
    "Volume",
    "Candle",
    "Green Count",
    "Red Count",
    "Neutral Count",
]

# Columns whose cells should wrap onto multiple lines within a single cell
WRAP_COLUMNS = {"EMA Ribbon"}

# Fill colors for bullish / bearish; neutral gets no fill
BULLISH_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
BEARISH_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
HEADER_FILL = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

# =========================
# CLIENT
# =========================
client = api(api_key=API_KEY, host=HOST)


def load_symbols(csv_path="all_symbols.csv"):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Symbol file not found: {csv_path}")

    df = pd.read_csv(csv_path, header=None, usecols=[0], names=["symbol"] )
    symbols = df["symbol"].astype(str).str.strip()
    symbols = symbols[symbols != ""].tolist()
    return symbols


def process_symbol(symbol, index, total):
    logger.info(f"Processing symbol {symbol} ({index}/{total})...")
    row = analyze_stock(symbol)
    return index, row


def main():
    try:
        logger.info("Starting the main function...")
        symbols = load_symbols()
        #symbols = ["ARENTERP", "ANDHRAPAP", "IEX", "ASHOKLEY", "UNIDT-BE", "ARVIND", "MAZDOCK", "ICEMAKE", "BPCL", "LIKHITHA-BE", "ABREL", "EVERESTIND", "622GS2035-GS", "EPL", "FINCABLES", "FEDERALBNK", "AARON", "ACCURACY", "GLOBAL", "HINDPETRO", "REPL-BE", "IFCI", "SHIVAMILLS-BE", "IFBIND", "RBA", "MOGSEC", "ASTERDM", "LYKALABS", "JBCHEPHARM", "KOTAKBANK", "KCP", "WEALTH", "CARYSIL", "LIQUIDETF", "KREBSBIO", "NELCO", "HEIDELBERG", "RAILTEL", "SANDHAR", "CONSUMBEES", "NILKAMAL", "CRAFTSMAN", "RALLIS", "SUDARSCHEM", "CORALFINAC", "SAMBHAAV", "CUBEXTUB", "SILINV", "REGENCERAM", "ZENITHEXPO", "RELINFRA-BE", "SAREGAMA", "FDC", "CYBERTECH", "RAJVIR-BZ", "CARTRADE", "FOCUS", "ARTNIRMAN", "NIFTYETF", "TECH", "LAXMICOT", "833GS2032-GS", "683GS2039-GS", "POLICYBZR", "923GS2043-GS", "773GS2034-GS", "761GS2030-GS", "697GS2026-GS", "679GS2029-GS", "668GS2031-GS", "817GS2044-GS", "759GS2029-GS", "772GS2055-GS", "MHLXMIRU", "SILVER", "AVANTIFEED", "CINEVISTA", "MAHLIFE", "KTKBANK", "MIDCAP", "DALBHARAT", "726GS2029-GS", "IDBIGOINAV", "GOLDSHINAV", "ICICISINAV", "GOLDBEINAV", "SILVERINAV", "AXISGOINAV", "NETFSIINAV", "IVZINGINAV", "BSLGOLINAV", "ICICIGINAV", "HDFCMFINAV", "KOTAKGINAV", "QGOLDHINAV", "SETFGOINAV", "RSSOFTWARE-BE", "GLFL-BE", "MIDCAPETF", "SGBMAR30X-GB", "VIPULLTD", "MITCON-BE", "XELPMOC", "BLUECHIP-BE", "TNIDETF", "PRIVISCL", "GAEL", "UMAEXPORTS-BE", "SUPERSPIN-BE", "VERANDA", "EUROTEXIND-BE", "E2E", "RITCO", "QUINTEGRA-BE", "NILAINFRA", "IOB", "TAJGVK", "ARROWGREEN-BE", "KRITIKA", "GOLDTECH", "BSLSENINAV", "AXISHCINAV", "ABSLNNINAV", "AXISBPINAV", "AXISCEINAV", "AXISBNINAV", "AXISNIINAV", "DSPN50INAV", "DSPNEWINAV", "EBANKINAV", "AXISTEINAV", "DSPQ50INAV", "LIQUIEINAV", "EBBE23INAV", "EBBE30INAV", "EBBE31INAV", "EBBE32INAV", "BBETF0INAV", "HBANKEINAV", "ICICIKINAV", "HDFCNFINAV", "HDFCSEINAV", "ICICIPINAV", "738GS2027-GS", "ICICIOINAV", "ICICI2INAV", "TECHINAV", "ABSLBAINAV", "VIKASLIFE", "HEALTHINAV", "BSLNIFINAV", "ICICITINAV", "ICICIXINAV", "ICICIQINAV", "ICICICINAV", "ICICIMINAV", "ICICIRINAV", "ICICI5INAV", "ICICIAINAV", "ICICIFINAV", "ICICIBINAV", "ICICIYINAV", "ICICININAV", "ICICI1INAV", "ICICILINAV", "IVZINNINAV", "KOTAKBINAV", "IBMFNIINAV", "IDFNIFINAV", "LICNFNINAV", "KOTAKPINAV", "KOTAKNINAV", "KOTAKVINAV", "KOTAKAINAV", "KOTAKMINAV", "KOTAKIINAV", "LICN50INAV", "KOTAKLINAV", "MAMFGEINAV", "MAN50EINAV", "MAFANGINAV", "MANXT5INAV", "LICNETINAV", "MAHKTEINAV", "MAFSETINAV", "LICNGSINAV", "MAM150INAV", "MOM50INAV", "MON100INAV", "MOLOWVINAV", "MONQ50INAV", "MOM100INAV", "MOGSECINAV", "MAESGEINAV", "MOMOMEINAV", "MASPTOINAV", "SDL26BINAV", "AUTOBEINAV", "PHARMAINAV", "QNIFTYINAV", "SDL24BINAV", "LTGILTINAV", "MID150INAV", "ITBEESINAV", "SETF10INAV", "SBILTYINAV", "SBICONINAV", "SETF50INAV", "NETFINAV", "SETFNIINAV", "NPBETINAV", "SETFNNINAV", "UTISENINAV", "UTINIFINAV", "UTINEXINAV", "UTISXNINAV", "ICISECINAV", "ICISENINAV", "PPL", "LIQUIDINAV", "GILT5YINAV", "SBIETFINAV", "SBIFPBINAV", "UNIVAFOODS-BE", "TNIDETINAV", "UTIBANINAV", "KOCONSINAV", "GUJGASLTD", "HDFC50INAV", "ICICMOINAV", "MOHLTHINAV", "HDF100INAV", "KOKMNCINAV", "NFQLTYINAV", "ICINFRINAV", "MOMNTMINAV", "DSPSILINAV", "HDFCSIINAV", "GFSTEELS-BE", "MOQLTYINAV", "NUCLEUS", "MOVALUINAV", "AXISILINAV", "GRMOVER", "GVPTECH", "HDFCVLINAV", "HDFCQUINAV", "BGLOBAL-BZ", "LUXIND", "HDFCGRINAV", "BALAXI-BE", "DHANBANK", "AFFLE", "HDFCMOINAV", "HDFCLVINAV", "HDFCSENSEX", "LINCOLN", "ASTRAMICRO", "KOTARISUG", "BOHRAIND", "BASML", "HDFCPBINAV", "ICIFININAV", "NAGAFERT-BZ", "AURIONPRO", "SYNCOMF", "ACI", "FAZE3Q", "IMPAL", "KOTAKSINAV", "IC10GSINAV", "PVRINOX", "EBB433INAV", "COMMOIETF", "RCOM-BE", "JAGRAN", "ICICOMINAV", "SGBSEP27-GB", "DSPBNKINAV", "MUNJALAU", "VIDHIING", "GMRAIRPORT", "CLCIND-BE", "HBS500INAV", "HSM250INAV", "HMI150INAV", "JASH", "KOTLIQINAV", "MAGOLDINAV", "VEEDOL", "726GS2033-GS", "ZEEMEDIA", "ABSLLQINAV", "PSBKICINAV", "POCL", "RAJTV", "AXSNSXINAV", "EMBDL", "GOKULAGRO", "MNV30FINAV", "MAG813INAV", "CENTRALBK", "SAHYADRI", "CIEINDIA", "PURVA", "KPRMILL", "INDOWIND-BE", "MOTILALOFS", "GSEC10YEAR", "729GR2033-GS", "710GR2028-GS", "SILETFINAV", "MADHAV", "SVLL-BE", "COLPAL", "KAUSHALYA", "DSPGOINAV", "PIGL", "KIRIINDUS", "PAVNAIND-BE", "EBBETF0430", "PRINCEPIPE", "VAISHALI-BE", "CCAVENUE", "MASILINAV", "DPWIRES", "HDFCNIINAV", "DSPNITINAV", "ARTEMISMED", "SICAGEN", "TPHQ", "THYROCARE", "SHARIABEES", "MAWANASUG-BE", "BNKETFINAV", "PVTBANKADD", "MGL", "AMRUTANJAN", "LIQUID", "SETCO-BE", "LIQIDINAV", "DAMODARIND", "INCREDIBLE", "DSPPVBINAV", "DSPSENINAV", "DSPPSBINAV", "ICIQ30INAV", "SARDAEN", "TREL", "QUAL30IETF", "LLOYDSENGG", "GILLANDERS", "DBCORP", "NIM150INAV", "VPRPL-BE", "HDFLIQINAV", "NAVNIFINAV", "NDGL", "PERSISTENT", "ASIANHOTNR", "UNIVASTU", "MON500INAV", "SENSEXINAV", "SICALLOG-BE", "HEADSUP", "ROLLT-BE", "UMESLTD", "NBIFIN", "SFL", "CMICABLES-BZ", "ALPHAINAV", "KALYANI-BE", "ITETFINAV", "HMT-BZ", "GPPL", "JITFINFRA", "LIQSBIINAV", "LIQUIDSBI", "BLUEJET", "EGOLDINAV", "AKSHARCHEM", "ESILINAV", "CLEDUCATE-BE", "OBEROIRLTY", "PRESTIGE", "SHAH", "ESILVER", "IREDA", "JWL", "GANDHAR", "724GR2033-GS", "BNGOLDINAV", "JINDWORLD", "SUPERHOUSE", "JAMNAAUTO", "BHAGYANGR-BE", "MOTISONS", "INOXINDIA", "SURAJEST", "HUDCO", "IRBINVIT-IV", "TAGOLDINAV", "TASILVINAV", "EDUCOMP-BZ", "LIQCASINAV", "ERIS", "JYOTICNC", "SALASAR", "PALASHSECU", "OPTIEMUS", "TATSILV", "BANKBINAV", "NIFTYBINAV", "NIFITEINAV", "NIF10GINAV", "HDFPBKINAV", "HEALADINAV", "NIF5GINAV", "LICNMDINAV", "MOREALINAV", "MOS250INAV", "LIQADDINAV", "CAPITALSFB", "LICNMID100", "GLDCASINAV", "EXICOM", "GPTHEALTH", "SMACAPINAV", "LIQETFINAV", "MIDSMAINAV", "ABSPSEINAV", "SKIL-BZ", "MD150CINAV", "TOP100INAV", "BBNPNBINAV", "SBISILINAV", "EVINDINAV", "ABGSECINAV", "SBINEQINAV", "OILETFINAV", "LIQSHRINAV", "ESTER", "RELIABLE", "OMINFRAL", "GROWEVINAV", "ASHIANA", "DELPHIFX", "METALIINAV", "GSEC10INAV", "MODEFINAV", "TOP10AINAV", "EBNKNFINAV", "GROLIQINAV", "MOME50INAV", "MULCAPINAV", "STYLEBAAZA-BE", "GALAPREC", "TOP10ADD", "EUREKAFORB", "GRWWDFINAV", "BNKPSUINAV", "METALINAV", "VAL30IINAV", "GROWWGINAV", "IMPEXFERRO-BZ", "EMLTMQINAV", "LIQPLSINAV", "SRPL-BZ", "AFCONS", "CONSUMINAV", "ECAPININAV", "664GS2027-GS", "ANUHPHR", "698GR2054-GS", "IGIL", "GRRAILINAV", "NX30ADINAV", "UNGOLDINAV", "MSCIININAV", "GRN200INAV", "NIF100INAV", "AONETOINAV", "EQU200INAV", "GLD360INAV", "SELIPOINAV", "AXISVAINAV", "CASHIEINAV", "SILCASINAV", "SBIBPBINAV", "MID15INAV", "AONELIINAV", "MOCAPIINAV", "AONETOTAL", "GOLD360", "SELECTIPO", "ATULAUTO", "EQUA50INAV", "MON50EINAV", "GROWMOINAV", "EVIETFINAV", "MINFRAINAV", "SIL360INAV", "MONT50INAV", "GROWSLINAV", "EQUAL200", "MOTOURINAV", "INTERNINAV", "MOPSEINAV", "TOPETFINAV", "GROWLOINAV", "MOMGFINAV", "AONENFINAV", "SNXT30INAV", "MOMIDMINAV", "GROWWNINAV", "GRWN50INAV", "MOALPHINAV", "MOSILVINAV", "QUALITINAV", "GRONIFINAV", "GROWWPINAV", "LIQGRBINAV", "ELM250INAV", "ELIQUIINAV", "SML100INAV", "MGBEESINAV", "AOGOLDINAV", "GROWWRINAV", "NIFTYCINAV", "MOY100INAV", "MOME30INAV", "FLEXIAINAV", "MOENERINAV", "CHGOLDINAV", "GRW150INAV", "GRO250INAV", "SMALL2INAV", "ENERGYINAV", "CHEMINAV", "ENIFTYINAV", "MOIPOINAV", "ESENSEINAV", "MSCIADINAV", "AONE50INAV", "MOSERVINAV", "MOMNCINAV", "GRCAPMINAV", "SMAADDINAV", "MIDADDINAV", "SILBNDINAV", "GOLDBDINAV", "NEXT50INAV", "DIVIDEINAV", "TWCGLDINAV", "TOP20INAV", "NEXT5EINAV", "GRWMTLINAV", "ABSMSCINAV", "HLTCREINAV", "INFRAINAV", "GRWCHEINAV", "GROWWEINAV", "DEFENCINAV", "GHOSPIINAV", "AB10BKINAV", "HSBCGDINAV", "SBIMOMINAV", "BNK10DINAV", "AONESIINAV", "LTCASEINAV", "SBILIQINAV", "MOGOLDINAV", "SBI150INAV", "VALUEINAV", "GRWPSUINAV", "MOBK10INAV", "VISL-BE", "VEDPOWER-BE", "VOGL-BE", "VAML-BE", "SMAETFINAV", "SMALLGINAV", "RAJOOENG", "NBCC", "MCX", "MTEDUCARE-BE", "SREEL", "RMDRIP", "ANTHEM", "CRIZAC", "EBGNG", "BELLACASA", "GROWWNET", "BORANA", "668GS2040-GS", "GENSOL-BZ", "AGSTRA-BZ", "REGAAL-BE", "ARFIN", "EFCIL", "CPPLUS", "SIMBHALS-BZ", "VIKRAMSOLR-BE", "ADVANCE", "FCONSUMER-BZ", "DIL-BZ", "KSR", "ESENSEX", "GROWWCAPM", "FABTECH", "BONLON", "SBIMIDMOM", "VITAL-BE", "AEPL", "RSL", "KOTYARK-BE", "MARSONS", "ASTAR", "BI", "BATLIBOI", "BTTL", "COCKERILL", "PRADPME", "TAMBOLIIN", "FMCGADINAV", "SBIVALINAV", "SBISMLINAV", "ENEXTINAV", "SHRIKRISH", "SEIL", "SHINDL", "SONAL", "MSC360INAV", "PTBKGRINAV", "THAKDEV", "THACKER-BE"]
        #symbols = ["TCS"]
        total = len(symbols)
        rows = []
        failed_symbols = []

        def process_symbol_batch(symbol_batch):
            processed_rows = []
            processed_failures = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(symbol_batch) or 1)) as executor:
                future_to_symbol = {
                    executor.submit(process_symbol, symbol, index, total): (index, symbol)
                    for index, symbol in symbol_batch
                }

                for future in concurrent.futures.as_completed(future_to_symbol):
                    index, symbol = future_to_symbol[future]
                    try:
                        _, row = future.result()
                    except Exception as e:
                        logger.exception(f"Error processing symbol {symbol}: {e}")
                        processed_failures.append(symbol)
                        continue
                    if row is not None:
                        processed_rows.append((index, row))
                    else:
                        processed_failures.append(symbol)

            return processed_rows, processed_failures

        initial_batch = [(index, symbol) for index, symbol in enumerate(symbols, start=1)]
        initial_rows, initial_failures = process_symbol_batch(initial_batch)
        rows.extend(initial_rows)

        if initial_failures:
            logger.info(f"Retrying {len(initial_failures)} symbols that returned no data: {initial_failures}")
            retry_rows, retry_failures = process_symbol_batch([(index, symbol) for index, symbol in initial_batch if symbol in initial_failures])
            rows.extend(retry_rows)

        rows.sort(key=lambda item: item[0])
        rows = [row for _, row in rows]
        write_excel(rows)

        if retry_failures:
            logger.warning(f"Symbols still without data after retry: {retry_failures}")

        if failed_symbols:
            logger.warning(f"Symbols with processing errors: {failed_symbols}")

    except Exception as e:
        logger.exception(f"Error in main: {e}")


def analyze_stock(symbol):
    # Fetch historical data for the symbol
    end = (datetime.now()).strftime("%Y-%m-%d")
    if datetime.now().hour < 18:  # If before 6 PM, use yesterday's date
        end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    

    start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")  # Last 100 days
    df = client.history(symbol=symbol, exchange="NSE", interval="D", start_date=start, end_date=end)

    if not hasattr(df, "columns") or df.empty:
        logger.warning(f"No data returned for {symbol}.")
        return None


    # Ensure required columns are present
    if not all(col in df.columns for col in required_cols):
        logger.warning(f"Data for {symbol} is missing required columns.")
        return None
    
    if df.empty or len(df) < 50:  # Ensure we have enough data points for analysis
        logger.warning(f"Not enough data for {symbol}. Required at least 50 data points, got {len(df) if not df.empty else 0}.")
        return None

    row = {"Symbol": {"value": symbol, "sentiment": "neutral"}}

    row["RSI5"], row["RSI5 Value"] = check_rsi(symbol, df, period=5)
    row["MACD"], row["MACD Value"] = check_macd(df)
    row["EMA Ribbon"] = check_ema(symbol, df)
    row["Stochastic"], row["Stochastic Value"] = check_stochastic(symbol, df)
    row["Volume"], row["Volume Value"] = check_volume(symbol, df)
    row["Candle"], row["Candle % Change"] = check_candle(symbol, df)

    factor_keys = ["RSI5", "MACD", "EMA Ribbon", "Stochastic", "Volume", "Candle"]
    counts = count_sentiments(row, factor_keys)
    row["Green Count"] = {"value": counts["bullish"], "sentiment": "neutral"}
    row["Red Count"] = {"value": counts["bearish"], "sentiment": "neutral"}
    row["Neutral Count"] = {"value": counts["neutral"], "sentiment": "neutral"}

    return row


def check_rsi(symbol, df, period=5):
    df["RSI5"] = ta.rsi(df["close"], period)
    rsi = df["RSI5"].iloc[-1]

    if rsi > 60:
        sentiment = "bullish"
        note = "OVERBOUGHT -> momentum stretched up, watch for a pullback"
    elif rsi < 40:
        sentiment = "bearish"
        note = "OVERSOLD -> momentum stretched down, watch for a bounce"
    else:
        sentiment = "neutral"
        note = "NEUTRAL (40-60) -> no extreme; 50 is the bull/bear line"

    value = f"{rsi:.2f} ({note})"
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": f"{rsi:.2f}", "sentiment": sentiment}
    return full, concise


def check_macd(df):
    macd_line, signal_line, hist = ta.macd(df["close"])

    m = macd_line.iloc[-1]
    s = signal_line.iloc[-1]
    h = hist.iloc[-1]

    sentiment = "bullish" if m > s else "bearish"
    momentum = "BULLISH (MACD above signal)" if m > s else "BEARISH (MACD below signal)"
    push = "strengthening" if h > 0 else "weakening / negative"

    value = f"MACD={m:.2f}, Signal={s:.2f}, Hist={h:.2f} | {momentum}, {push}"
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": f"MACD={m:.2f}, Signal={s:.2f}", "sentiment": sentiment}
    return full, concise


def check_ema(symbol, df):
    periods = [5, 13, 26, 50]
    emas = {p: ta.ema(df["close"], p).iloc[-1] for p in periods}

    # A bullish stack means fast EMAs sit above slow EMAs, in order.
    ordered = [emas[p] for p in periods]
    stacked_up = all(ordered[i] > ordered[i + 1] for i in range(len(ordered) - 1))
    stacked_down = all(ordered[i] < ordered[i + 1] for i in range(len(ordered) - 1))

    if stacked_up:
        sentiment = "bullish"
        note = "bullish stack"
    elif stacked_down:
        sentiment = "bearish"
        note = "bearish stack"
    else:
        sentiment = "neutral"
        note = "tangled / no clear trend"

    lines = [f"Close={df['close'].iloc[-1]:.2f}"]
    lines += [f"EMA{p}={emas[p]:.2f}" for p in periods]
    lines.append(note)
    value = "\n".join(lines)
    return {"value": value, "sentiment": sentiment}


def check_stochastic(symbol, df):
    k, d = ta.stochastic(df["high"], df["low"], df["close"], k_period=5, d_period=3)

    kv = k.iloc[-1]
    dv = d.iloc[-1]

    if kv > 80:
        zone = "OVERBOUGHT (>80)"
    elif kv < 20:
        zone = "OVERSOLD (<20)"
    else:
        zone = "mid-range (20-80)"

    sentiment = "bullish" if kv > dv else "bearish"
    cross = "%K above %D -> bullish tilt" if kv > dv else "%K below %D -> bearish tilt"

    value = f"%K={kv:.2f}, %D={dv:.2f} | {zone} | {cross}"
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": f"%K={kv:.2f}, %D={dv:.2f}", "sentiment": sentiment}
    return full, concise


def count_sentiments(row, factor_keys):
    sentiments = [row[key].get("sentiment", "neutral") for key in factor_keys if isinstance(row.get(key), dict)]
    return {
        "bullish": sum(1 for s in sentiments if s == "bullish"),
        "bearish": sum(1 for s in sentiments if s == "bearish"),
        "neutral": sum(1 for s in sentiments if s == "neutral"),
    }


def check_volume(symbol, df):
    prev_volume = df["volume"].iloc[-2]
    current_volume = df["volume"].iloc[-1]

    if current_volume > prev_volume and current_volume > 100000:
        sentiment = "bullish"
        note = "Volume is increasing -> bullish tilt"
    elif current_volume > prev_volume and current_volume <= 100000:
        sentiment = "neutral"
        note = "Volume increasing but below threshold -> cautious bullish tilt"
    else:
        sentiment = "bearish"
        note = "Volume is decreasing -> bearish tilt"

    value = f"Current={current_volume:,}, Prev={prev_volume:,} | {note}"
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": f"Current={current_volume:,}, Prev={prev_volume:,}", "sentiment": sentiment}
    return full, concise


def check_candle(symbol, df):
    # Bullish if close is 5%+ above open, bearish if close is 5%+ below open
    last_candle = df.iloc[-1]
    open_price = last_candle["open"]
    close_price = last_candle["close"]
    high_price = last_candle["high"]
    low_price = last_candle["low"]
 
    if open_price == 0:
        na = {"value": "N/A (zero open)", "sentiment": "neutral"}
        return na, na

    pct_change = (close_price - open_price) / open_price * 100

    if pct_change > 5:
        sentiment = "bullish"
        note = f"Close is {pct_change:.2f}% above open -> bullish"
    elif pct_change < -5:
        sentiment = "bearish"
        note = f"Close is {abs(pct_change):.2f}% below open -> bearish"
    else:
        sentiment = "neutral"
        note = f"Close is {pct_change:.2f}% vs open -> within +/-5% range"

    value = f"O={open_price:,.2f} H={high_price:,.2f} L={low_price:,.2f} C={close_price:,.2f} | {note}"
    full = {"value": value, "sentiment": sentiment}
    concise = {"value": pct_change, "sentiment": sentiment}
    return full, concise


def write_excel(rows):
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Strategy Output"

    # Header row
    for col_idx, col_name in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=col_idx, value=col_name)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        for col_idx, col_name in enumerate(COLUMNS, start=1):
            cell_data = row.get(col_name, {"value": "", "sentiment": "neutral"})
            cell = sheet.cell(row=row_idx, column=col_idx, value=cell_data["value"])
            if cell_data["sentiment"] == "bullish":
                cell.fill = BULLISH_FILL
            elif cell_data["sentiment"] == "bearish":
                cell.fill = BEARISH_FILL
            cell.font = Font(name="Arial")
            if col_name in WRAP_COLUMNS:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

        # Give the EMA row enough height to show its multi-line content
        sheet.row_dimensions[row_idx].height = 90

    # Reasonable column widths: Symbol, concise columns, detailed columns, and sentiment counts
    widths = [14, 14, 14, 55, 14, 14, 14, 40, 46, 30, 30, 60, 12, 12, 12]
    for col_idx, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=col_idx).column_letter].width = width

    wb.save(OUTPUT_FILE)
    logger.info(f"✅ Excel report written to {OUTPUT_FILE}")


if __name__ == "__main__":
    start_time = time.perf_counter()
    main()
    elapsed = time.perf_counter() - start_time
    logger.info(f"Total runtime: {elapsed:.2f} seconds")