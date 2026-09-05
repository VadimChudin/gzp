//+------------------------------------------------------------------+
//|                                                    GZP_Zones.mq4 |
//|                          GZP — Gold Zone Pro. Индикатор сильных   |
//|                          ценовых зон по конфлюенсу H4 / H1 / S-R. |
//|                                                                  |
//| Индикатор ничего не считает сам: он читает zones_gzp.json,        |
//| который пишет Python-ядро GZP, и отрисовывает зоны.              |
//| Торговых сигналов индикатор не показывает принципиально (ТЗ §59). |
//+------------------------------------------------------------------+
#property copyright "GZP — Gold Zone Pro"
#property version   "1.00"
#property strict
#property indicator_chart_window

// Номер сборки подставляет CI при компиляции релиза.
#define GZP_BUILD_STAMP "R3"
#define GZP_SCHEMA      1
#define PREFIX          "GZP_"

input string  DataFile        = "GZP\\zones_gzp.json"; // Файл зон (MQL4/Files)
input int     RefreshSeconds  = 5;                     // Период проверки файла
input bool    ShowPanel       = true;                  // Панель версии на графике
input bool    ShowReference   = true;                  // Линия reference-уровня
input bool    ShowLabels      = true;                  // Подписи зон
input int     ZoneExtendBars  = 40;                    // Продление зоны вправо
input color   ColorStrong     = C'196,158,42';         // Strong
input color   ColorVeryStrong = C'242,206,110';        // Very Strong
input color   ColorTested     = C'150,140,120';        // Уже тестированная
input int     ZoneOpacity     = 1;                     // Толщина рамки

// Данные зон
double  zLower[], zUpper[], zRef[], zScore[];
string  zId[], zGrade[], zState[], zLabel[];
datetime zCreated[];
int      zCount = 0;

string  fileVersion = "";
string  fileRelease = "";
string  fileSymbol  = "";
string  fileStamp   = "";
datetime lastLoad   = 0;
string  lastPayloadHash = "";

//+------------------------------------------------------------------+
int OnInit()
  {
   IndicatorShortName("GZP Zones " + GZP_BUILD_STAMP);
   EventSetTimer(MathMax(1, RefreshSeconds));
   LoadAndDraw();
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   CleanObjects();
   Comment("");
  }

void OnTimer()
  {
   LoadAndDraw();
  }

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   // Перерисовываем при появлении новых баров, чтобы зоны тянулись вправо.
   if(prev_calculated == 0 || rates_total != prev_calculated)
      DrawZones();
   return(rates_total);
  }

//+------------------------------------------------------------------+
//| Чтение файла и отрисовка                                          |
//+------------------------------------------------------------------+
void LoadAndDraw()
  {
   string payload = ReadFileText(DataFile);
   if(StringLen(payload) == 0)
     {
      ShowStatus("GZP: файл зон не найден — запустите приложение GZP");
      return;
     }

   // Не перерисовываем, если содержимое не изменилось.
   string stamp = ExtractString(payload, "generated_at");
   if(stamp == lastPayloadHash && zCount > 0)
     {
      DrawZones();
      return;
     }
   lastPayloadHash = stamp;

   int schema = (int)ExtractNumber(payload, "schema", 0, -1);
   if(schema != GZP_SCHEMA)
     {
      ShowStatus(StringFormat("GZP: несовместимая схема данных (%d, нужна %d)",
                              schema, GZP_SCHEMA));
      return;
     }

   fileVersion = ExtractString(payload, "version");
   fileRelease = ExtractString(payload, "release");
   fileSymbol  = ExtractString(payload, "symbol");
   fileStamp   = stamp;

   ParseZones(payload);
   lastLoad = TimeCurrent();
   DrawZones();
  }

string ReadFileText(string relativePath)
  {
   int handle = FileOpen(relativePath, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(handle == INVALID_HANDLE)
      return("");

   string content = "";
   while(!FileIsEnding(handle))
      content += FileReadString(handle);
   FileClose(handle);
   return(content);
  }

//+------------------------------------------------------------------+
//| Минимальный разбор JSON под известную схему GZP                   |
//+------------------------------------------------------------------+
void ParseZones(string payload)
  {
   zCount = 0;
   int zonesPos = StringFind(payload, "\"zones\"");
   if(zonesPos < 0)
      return;

   int cursor = zonesPos;
   int guard  = 0;
   while(guard < 64)
     {
      guard++;
      int objStart = StringFind(payload, "{", cursor);
      if(objStart < 0)
         break;
      int objEnd = FindObjectEnd(payload, objStart);
      if(objEnd < 0)
         break;

      string obj = StringSubstr(payload, objStart, objEnd - objStart + 1);
      // Вложенные объекты (confirmations, score_breakdown) отсекаются тем,
      // что мы ищем ключи верхнего уровня и берём первое вхождение.
      if(StringFind(obj, "\"reference\"") >= 0)
         AppendZone(obj);

      cursor = objEnd + 1;
      if(zCount >= 64)
         break;
     }
  }

int FindObjectEnd(string text, int start)
  {
   int depth = 0;
   int len = StringLen(text);
   for(int i = start; i < len; i++)
     {
      string ch = StringSubstr(text, i, 1);
      if(ch == "{")
         depth++;
      else if(ch == "}")
        {
         depth--;
         if(depth == 0)
            return(i);
        }
     }
   return(-1);
  }

void AppendZone(string obj)
  {
   int i = zCount;
   ArrayResize(zLower, i + 1);
   ArrayResize(zUpper, i + 1);
   ArrayResize(zRef, i + 1);
   ArrayResize(zScore, i + 1);
   ArrayResize(zId, i + 1);
   ArrayResize(zGrade, i + 1);
   ArrayResize(zState, i + 1);
   ArrayResize(zLabel, i + 1);
   ArrayResize(zCreated, i + 1);

   zLower[i]   = ExtractNumber(obj, "lower", 0, 0);
   zUpper[i]   = ExtractNumber(obj, "upper", 0, 0);
   zRef[i]     = ExtractNumber(obj, "reference", 0, 0);
   zScore[i]   = ExtractNumber(obj, "score", 0, 0);
   zId[i]      = ExtractString(obj, "id");
   zGrade[i]   = ExtractString(obj, "grade");
   zState[i]   = ExtractString(obj, "state");
   zCreated[i] = ParseIsoTime(ExtractString(obj, "created_at"));

   int h4 = (int)ExtractNumber(obj, "\"h4\"", 0, 0);
   int h1 = (int)ExtractNumber(obj, "\"h1\"", 0, 0);
   int sr = (int)ExtractNumber(obj, "\"sr\"", 0, 0);
   int tests = (int)ExtractNumber(obj, "tests", 0, 0);

   string src = "";
   if(h4 > 0) src += StringFormat("H4x%d ", h4);
   if(h1 > 0) src += StringFormat("H1x%d ", h1);
   if(sr > 0) src += "SR ";
   string grade = (zGrade[i] == "very_strong") ? "VERY STRONG" : "STRONG";

   zLabel[i] = StringFormat("%s  %.2f  %s| S:%.0f | T%d",
                            grade, zRef[i], src, zScore[i], tests);
   if(zLower[i] > 0 && zUpper[i] > zLower[i])
      zCount++;
  }

double ExtractNumber(string text, string key, int from, double fallback)
  {
   string needle = (StringFind(key, "\"") == 0) ? key : "\"" + key + "\"";
   int pos = StringFind(text, needle, from);
   if(pos < 0)
      return(fallback);
   int colon = StringFind(text, ":", pos);
   if(colon < 0)
      return(fallback);

   string buf = "";
   int len = StringLen(text);
   for(int i = colon + 1; i < len; i++)
     {
      string ch = StringSubstr(text, i, 1);
      if(ch == " " || ch == "\n" || ch == "\r" || ch == "\t")
        {
         if(StringLen(buf) > 0) break;
         continue;
        }
      if(ch == "," || ch == "}" || ch == "]")
         break;
      buf += ch;
     }
   if(StringLen(buf) == 0)
      return(fallback);
   return(StrToDouble(buf));
  }

string ExtractString(string text, string key)
  {
   string needle = "\"" + key + "\"";
   int pos = StringFind(text, needle);
   if(pos < 0)
      return("");
   int colon = StringFind(text, ":", pos);
   if(colon < 0)
      return("");
   int first = StringFind(text, "\"", colon + 1);
   if(first < 0)
      return("");
   int last = StringFind(text, "\"", first + 1);
   if(last < 0)
      return("");
   return(StringSubstr(text, first + 1, last - first - 1));
  }

datetime ParseIsoTime(string iso)
  {
   // "2026-04-20T08:00:00+00:00" → "2026.04.20 08:00:00"
   if(StringLen(iso) < 19)
      return(0);
   string date = StringSubstr(iso, 0, 10);
   string clock = StringSubstr(iso, 11, 8);
   StringReplace(date, "-", ".");
   return(StrToTime(date + " " + clock));
  }

//+------------------------------------------------------------------+
//| Отрисовка                                                         |
//+------------------------------------------------------------------+
void DrawZones()
  {
   CleanObjects();

   datetime rightEdge = Time[0] + PeriodSeconds() * ZoneExtendBars;
   for(int i = 0; i < zCount; i++)
     {
      color zoneColor = ColorStrong;
      if(zGrade[i] == "very_strong") zoneColor = ColorVeryStrong;
      if(zState[i] == "tested")      zoneColor = ColorTested;

      datetime left = zCreated[i];
      if(left <= 0 || left < Time[WindowFirstVisibleBar()])
         left = Time[MathMin(WindowFirstVisibleBar(), Bars - 1)];

      string rectName = PREFIX + "zone_" + IntegerToString(i);
      ObjectCreate(0, rectName, OBJ_RECTANGLE, 0, left, zLower[i], rightEdge, zUpper[i]);
      ObjectSetInteger(0, rectName, OBJPROP_COLOR, zoneColor);
      ObjectSetInteger(0, rectName, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, rectName, OBJPROP_WIDTH, ZoneOpacity);
      ObjectSetInteger(0, rectName, OBJPROP_BACK, true);
      ObjectSetInteger(0, rectName, OBJPROP_SELECTABLE, false);

      if(ShowReference)
        {
         string refName = PREFIX + "ref_" + IntegerToString(i);
         ObjectCreate(0, refName, OBJ_TREND, 0, left, zRef[i], rightEdge, zRef[i]);
         ObjectSetInteger(0, refName, OBJPROP_COLOR, zoneColor);
         ObjectSetInteger(0, refName, OBJPROP_STYLE, STYLE_DOT);
         ObjectSetInteger(0, refName, OBJPROP_WIDTH, 1);
         ObjectSetInteger(0, refName, OBJPROP_RAY_RIGHT, false);
         ObjectSetInteger(0, refName, OBJPROP_BACK, true);
         ObjectSetInteger(0, refName, OBJPROP_SELECTABLE, false);
        }

      if(ShowLabels)
        {
         string txtName = PREFIX + "lbl_" + IntegerToString(i);
         ObjectCreate(0, txtName, OBJ_TEXT, 0, rightEdge, zUpper[i]);
         ObjectSetString(0, txtName, OBJPROP_TEXT, zLabel[i]);
         ObjectSetInteger(0, txtName, OBJPROP_COLOR, zoneColor);
         ObjectSetInteger(0, txtName, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(0, txtName, OBJPROP_ANCHOR, ANCHOR_RIGHT_LOWER);
         ObjectSetInteger(0, txtName, OBJPROP_SELECTABLE, false);
        }
     }

   if(ShowPanel)
      DrawPanel();
   ChartRedraw();
  }

void DrawPanel()
  {
   string name = PREFIX + "panel";
   string text = StringFormat("GZP v%s %s  |  %s  |  зон: %d  |  %s",
                              fileVersion == "" ? "?" : fileVersion,
                              fileRelease == "" ? GZP_BUILD_STAMP : fileRelease,
                              fileSymbol == "" ? Symbol() : fileSymbol,
                              zCount,
                              StringSubstr(fileStamp, 11, 8));
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 12);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 16);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
   ObjectSetInteger(0, name, OBJPROP_COLOR, ColorVeryStrong);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void ShowStatus(string message)
  {
   string name = PREFIX + "status";
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 12);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 16);
   ObjectSetString(0, name, OBJPROP_TEXT, message);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clrGoldenrod);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ChartRedraw();
  }

void CleanObjects()
  {
   for(int i = ObjectsTotal() - 1; i >= 0; i--)
     {
      string name = ObjectName(i);
      if(StringFind(name, PREFIX) == 0)
         ObjectDelete(name);
     }
  }
//+------------------------------------------------------------------+
