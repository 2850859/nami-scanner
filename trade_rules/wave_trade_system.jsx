/**
 * nami-scanner / trade_rules に同梱の検証用 UI（AI生成版を引用）。
 * 実行には React + recharts + lucide-react が必要です。
 * 本番ロジック・仕様のソースオブトゥルースは backtest_engine.py と system_spec.md です。
 */
import React, { useState, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, ReferenceLine, Legend } from 'recharts';
import { TrendingUp, TrendingDown, Activity, Target, Shield, AlertCircle, Play, RotateCcw, ChevronRight, Zap } from 'lucide-react';

// ============================================
// 統合戦略エンジン: 波乗り × cleartrade
// ============================================

// 疑似乱数 (シード付きで再現可能)
const seedRandom = (seed) => {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
};

// 銘柄ごとに性格付けされた価格データ生成
const generateStockData = (config, days = 750) => {
  const rng = seedRandom(config.seed);
  const data = [];
  let price = config.startPrice;
  let trend = 0;
  let volRegime = 1;

  for (let i = 0; i < days; i++) {
    // トレンドレジームの変化
    if (rng() < 0.015) trend = (rng() - 0.5) * config.trendStrength;
    if (rng() < 0.02) volRegime = 0.7 + rng() * 1.5;

    // 日次リターン
    const noise = (rng() - 0.5) * config.volatility * volRegime;
    const dailyReturn = trend / 100 + noise;
    price = price * (1 + dailyReturn);

    // OHLC
    const range = price * config.volatility * volRegime * 0.7;
    const open = price - range * (rng() - 0.5);
    const high = Math.max(open, price) + range * rng() * 0.5;
    const low = Math.min(open, price) - range * rng() * 0.5;

    // 出来高 (大きな動きの日は出来高増)
    const volMultiplier = 1 + Math.abs(dailyReturn) * 30 + (rng() - 0.5) * 0.4;
    const volume = Math.max(0.3, config.baseVolume * volMultiplier);

    data.push({
      day: i,
      date: new Date(2023, 0, 1 + i).toISOString().slice(0, 10),
      open: parseFloat(open.toFixed(2)),
      high: parseFloat(high.toFixed(2)),
      low: parseFloat(low.toFixed(2)),
      close: parseFloat(price.toFixed(2)),
      volume: parseFloat(volume.toFixed(2)),
    });
  }
  return data;
};

// テクニカル計算ユーティリティ
const sma = (arr, key, period, idx) => {
  if (idx < period - 1) return null;
  let sum = 0;
  for (let i = idx - period + 1; i <= idx; i++) sum += arr[i][key];
  return sum / period;
};

const max = (arr, key, period, idx) => {
  if (idx < period - 1) return null;
  let m = -Infinity;
  for (let i = idx - period + 1; i <= idx; i++) m = Math.max(m, arr[i][key]);
  return m;
};

// 直近ピーク日: 過去20日で出来高最大かつ価格高値日（両方満たす日）
const findPeakDay = (data, idx) => {
  if (idx < 20) return null;
  let maxVol = -1, maxVolDay = -1;
  let maxPrice = -1, maxPriceDay = -1;
  for (let i = idx - 19; i <= idx; i++) {
    if (data[i].volume > maxVol) { maxVol = data[i].volume; maxVolDay = i; }
    if (data[i].high > maxPrice) { maxPrice = data[i].high; maxPriceDay = i; }
  }
  return maxVolDay === maxPriceDay ? { day: maxVolDay, volume: maxVol, price: maxPrice } : null;
};

// シグナル強度スコア
const calcSignalScore = (volRatio, ret20, dipPct) => {
  const volScore = 0.4 * (volRatio - 2.0);
  const retScore = 0.3 * (ret20 - 0.05) * 10;
  const dipScore = 0.3 * (1 - Math.abs(dipPct + 0.04) / 0.01);
  return volScore + retScore + dipScore;
};

// メインシグナル検出ロジック
const detectSignals = (stockData, topixData) => {
  const signals = [];
  for (let i = 25; i < stockData.length - 1; i++) {
    const d = stockData[i];

    // S: スクリーニング
    const volSMA20 = sma(stockData, 'volume', 20, i);
    const high20 = max(stockData, 'high', 20, i);
    const close20Ago = stockData[i - 20].close;
    const ret20 = (d.close / close20Ago) - 1;

    if (!volSMA20 || !high20) continue;
    const S1 = (d.volume / volSMA20) >= 2.0;
    const S2 = d.close >= high20;
    const S3 = ret20 >= 0.05;

    // T: トレンドフィルター
    const closeSMA20 = sma(stockData, 'close', 20, i);
    const topixSMA20 = sma(topixData, 'close', 20, i);
    const T1 = d.close > closeSMA20;
    const T2 = topixData[i].close > topixSMA20;

    // P: 押し目検出 (10日高値基準)
    const high10 = max(stockData, 'high', 10, i);
    const dipPct = (d.close / high10) - 1;
    const P1 = dipPct >= -0.05 && dipPct <= -0.03;

    const peak = findPeakDay(stockData, i);
    const volSMA5 = sma(stockData, 'volume', 5, i);
    const P2 = peak && volSMA5 < 0.7 * peak.volume;
    const P3 = d.close >= closeSMA20;

    // E: トリガー
    const E1 = i > 0 && d.close > stockData[i - 1].high;
    const E2 = i > 0 &&
      d.open < stockData[i - 1].close &&
      d.close > stockData[i - 1].open &&
      d.close > d.open;

    // 除外ルール
    const gap = i > 0 ? (d.open / stockData[i - 1].close) - 1 : 0;
    const gapExclude = gap >= 0.05;
    const negVolExclude = d.close < d.open && d.volume > volSMA20;

    const passScreen = S1 && S2 && S3;
    const passTrend = T1 && T2;
    const passDip = P1 && P2 && P3;
    const passTrigger = E1 || E2;
    const noExclude = !gapExclude && !negVolExclude;

    if (passScreen && passTrend && passDip && passTrigger && noExclude) {
      signals.push({
        idx: i,
        date: d.date,
        entryPrice: stockData[i + 1].open,
        signalScore: calcSignalScore(d.volume / volSMA20, ret20, dipPct),
        volRatio: d.volume / volSMA20,
        ret20,
        dipPct,
        triggerType: E1 ? 'ブレイク' : '包み足',
      });
    }
  }
  return signals;
};

// バックテスト実行
const runBacktest = (allStockData, topixData, config) => {
  const allSignals = [];
  Object.entries(allStockData).forEach(([code, data]) => {
    const sigs = detectSignals(data, topixData);
    sigs.forEach(s => allSignals.push({ ...s, code, stockData: data }));
  });
  allSignals.sort((a, b) => a.idx - b.idx);

  let capital = config.initialCapital;
  const trades = [];
  const equity = [{ day: 0, value: capital }];
  const positions = {}; // code -> position

  const days = topixData.length;

  for (let day = 0; day < days; day++) {
    // 既存ポジションの管理
    Object.keys(positions).forEach(code => {
      const pos = positions[code];
      const data = allStockData[code];
      if (day <= pos.entryDay || day >= data.length) return;
      const d = data[day];

      // 損切り
      if (d.close <= pos.entryPrice * 0.95) {
        if (day + 1 < data.length) {
          const exitPrice = data[day + 1].open;
          const pnl = (exitPrice - pos.entryPrice) * pos.shares - (exitPrice + pos.entryPrice) * pos.shares * 0.0005;
          capital += exitPrice * pos.shares;
          trades.push({ ...pos, exitDay: day + 1, exitPrice, exitReason: '損切り', pnl, pnlPct: (exitPrice / pos.entryPrice - 1) });
          delete positions[code];
        }
        return;
      }

      // 第一利確
      if (!pos.tp1Done && d.close >= pos.entryPrice * 1.10) {
        if (day + 1 < data.length) {
          const exitPrice = data[day + 1].open;
          const halfShares = Math.floor(pos.shares / 2);
          const pnl = (exitPrice - pos.entryPrice) * halfShares - (exitPrice + pos.entryPrice) * halfShares * 0.0005;
          capital += exitPrice * halfShares;
          trades.push({ ...pos, shares: halfShares, exitDay: day + 1, exitPrice, exitReason: 'TP1', pnl, pnlPct: (exitPrice / pos.entryPrice - 1) });
          pos.shares -= halfShares;
          pos.tp1Done = true;
        }
        return;
      }

      // トレーリング: 5日線 or 建値の高い方
      if (pos.tp1Done) {
        const sma5 = sma(data, 'close', 5, day);
        const stopLevel = Math.max(sma5 || 0, pos.entryPrice);
        if (d.close < stopLevel && day + 1 < data.length) {
          const exitPrice = data[day + 1].open;
          const pnl = (exitPrice - pos.entryPrice) * pos.shares - (exitPrice + pos.entryPrice) * pos.shares * 0.0005;
          capital += exitPrice * pos.shares;
          trades.push({ ...pos, exitDay: day + 1, exitPrice, exitReason: 'トレール', pnl, pnlPct: (exitPrice / pos.entryPrice - 1) });
          delete positions[code];
        }
      } else {
        // TP1未到達でも5日線割れでトレール (利益保護)
        const sma5 = sma(data, 'close', 5, day);
        if (sma5 && d.close < sma5 && d.close > pos.entryPrice * 1.05 && day + 1 < data.length) {
          const exitPrice = data[day + 1].open;
          const pnl = (exitPrice - pos.entryPrice) * pos.shares - (exitPrice + pos.entryPrice) * pos.shares * 0.0005;
          capital += exitPrice * pos.shares;
          trades.push({ ...pos, exitDay: day + 1, exitPrice, exitReason: '早期トレール', pnl, pnlPct: (exitPrice / pos.entryPrice - 1) });
          delete positions[code];
        }
      }
    });

    // この日のシグナル収集
    const todaySignals = allSignals.filter(s => s.idx === day && !positions[s.code]);
    if (todaySignals.length === 0) continue;

    // シグナル強度でソート
    todaySignals.sort((a, b) => b.signalScore - a.signalScore);

    // ポジション枠と入れ替え判定
    for (const sig of todaySignals) {
      if (Object.keys(positions).length < 3) {
        // 空き枠あり
        const totalEquity = capital + Object.values(positions).reduce((sum, p) => {
          const cd = allStockData[p.code][day];
          return sum + (cd ? cd.close * p.shares : 0);
        }, 0);
        const riskAmount = totalEquity * (config.riskPerTrade / 100);
        const shares = Math.floor(riskAmount / (sig.entryPrice * 0.05));
        if (shares > 0 && capital >= sig.entryPrice * shares) {
          capital -= sig.entryPrice * shares;
          positions[sig.code] = {
            code: sig.code,
            entryDay: day + 1,
            entryPrice: sig.entryPrice,
            shares,
            signalScore: sig.signalScore,
            entryDate: sig.date,
            tp1Done: false,
          };
        }
      } else {
        // 枠フル: 最弱ポジションと比較
        const weakestCode = Object.keys(positions).reduce((w, c) =>
          positions[c].signalScore < positions[w].signalScore ? c : w
        );
        if (sig.signalScore > positions[weakestCode].signalScore * 1.2) {
          // 入れ替え (20%以上強いシグナルのみ)
          const wp = positions[weakestCode];
          const data = allStockData[weakestCode];
          if (day + 1 < data.length) {
            const exitPrice = data[day + 1].open;
            const pnl = (exitPrice - wp.entryPrice) * wp.shares;
            capital += exitPrice * wp.shares;
            trades.push({ ...wp, exitDay: day + 1, exitPrice, exitReason: '入替', pnl, pnlPct: (exitPrice / wp.entryPrice - 1) });
            delete positions[weakestCode];

            const totalEquity = capital;
            const riskAmount = totalEquity * (config.riskPerTrade / 100);
            const shares = Math.floor(riskAmount / (sig.entryPrice * 0.05));
            if (shares > 0 && capital >= sig.entryPrice * shares) {
              capital -= sig.entryPrice * shares;
              positions[sig.code] = {
                code: sig.code,
                entryDay: day + 1,
                entryPrice: sig.entryPrice,
                shares,
                signalScore: sig.signalScore,
                entryDate: sig.date,
                tp1Done: false,
              };
            }
          }
        }
      }
    }

    // エクイティ記録
    const totalEquity = capital + Object.values(positions).reduce((sum, p) => {
      const cd = allStockData[p.code][day];
      return sum + (cd ? cd.close * p.shares : 0);
    }, 0);
    equity.push({ day, value: totalEquity, date: topixData[day].date });
  }

  return { trades, equity, finalCapital: equity[equity.length - 1].value };
};

// ============================================
// メインコンポーネント
// ============================================

const stockConfigs = [
  { code: '7203', name: 'トヨタ風', seed: 101, startPrice: 2500, volatility: 0.018, trendStrength: 0.8, baseVolume: 100 },
  { code: '6758', name: 'ソニー風', seed: 202, startPrice: 12000, volatility: 0.025, trendStrength: 1.2, baseVolume: 80 },
  { code: '9984', name: 'SBG風', seed: 303, startPrice: 6500, volatility: 0.035, trendStrength: 1.5, baseVolume: 120 },
  { code: '6861', name: 'キーエンス風', seed: 404, startPrice: 65000, volatility: 0.022, trendStrength: 1.0, baseVolume: 50 },
  { code: '8035', name: '東エレ風', seed: 505, startPrice: 25000, volatility: 0.030, trendStrength: 1.3, baseVolume: 70 },
  { code: '4063', name: '信越化風', seed: 606, startPrice: 5500, volatility: 0.020, trendStrength: 0.9, baseVolume: 60 },
];

export default function WaveTradeSystem() {
  const [activeTab, setActiveTab] = useState('overview');
  const [riskPerTrade, setRiskPerTrade] = useState(0.2);
  const [initialCapital, setInitialCapital] = useState(100000000);
  const [hasRun, setHasRun] = useState(false);

  const { allStockData, topixData } = useMemo(() => {
    const stocks = {};
    stockConfigs.forEach(c => { stocks[c.code] = generateStockData(c, 750); });
    const topix = generateStockData({ seed: 999, startPrice: 2000, volatility: 0.012, trendStrength: 0.5, baseVolume: 1000 }, 750);
    return { allStockData: stocks, topixData: topix };
  }, []);

  const result = useMemo(() => {
    if (!hasRun) return null;
    return runBacktest(allStockData, topixData, { initialCapital, riskPerTrade });
  }, [hasRun, allStockData, topixData, initialCapital, riskPerTrade]);

  // 統計計算
  const stats = useMemo(() => {
    if (!result) return null;
    const { trades, equity, finalCapital } = result;
    const totalReturn = (finalCapital / initialCapital - 1) * 100;
    const closedTrades = trades.filter(t => t.pnl !== undefined);
    const wins = closedTrades.filter(t => t.pnl > 0);
    const losses = closedTrades.filter(t => t.pnl <= 0);
    const winRate = closedTrades.length > 0 ? (wins.length / closedTrades.length) * 100 : 0;
    const avgWin = wins.length ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0;
    const avgLoss = losses.length ? Math.abs(losses.reduce((s, t) => s + t.pnl, 0) / losses.length) : 1;
    const rr = avgWin / avgLoss;
    const totalWin = wins.reduce((s, t) => s + t.pnl, 0);
    const totalLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0));
    const pf = totalLoss > 0 ? totalWin / totalLoss : 0;

    // 最大ドローダウン
    let peak = equity[0].value, maxDD = 0;
    equity.forEach(e => {
      if (e.value > peak) peak = e.value;
      const dd = (peak - e.value) / peak * 100;
      if (dd > maxDD) maxDD = dd;
    });

    const years = equity.length / 250;
    const annualReturn = (Math.pow(finalCapital / initialCapital, 1 / years) - 1) * 100;

    return {
      totalReturn, annualReturn, maxDD, winRate, rr, pf,
      tradeCount: closedTrades.length,
      finalCapital,
    };
  }, [result, initialCapital]);

  const equityChartData = useMemo(() => {
    if (!result) return [];
    return result.equity.filter((_, i) => i % 5 === 0).map(e => ({
      day: e.day,
      value: Math.round(e.value / 1000000),
    }));
  }, [result]);

  const monthlyReturns = useMemo(() => {
    if (!result) return [];
    const monthly = {};
    result.equity.forEach((e, i) => {
      if (!e.date) return;
      const month = e.date.slice(0, 7);
      if (!monthly[month]) monthly[month] = { start: e.value, end: e.value };
      monthly[month].end = e.value;
    });
    return Object.entries(monthly).map(([month, v]) => ({
      month: month.slice(2),
      ret: ((v.end / v.start - 1) * 100),
    })).slice(0, 36);
  }, [result]);

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900" style={{ fontFamily: "'Noto Serif JP', Georgia, serif" }}>
      {/* Header */}
      <header className="border-b-2 border-stone-900 bg-stone-50 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">波乗り × cleartrade</h1>
              <p className="text-xs text-stone-600 mt-1 tracking-widest uppercase">Integrated Strategy Backtester</p>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-xs text-stone-500 tracking-wider">v1.0 / 検証モード</span>
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <nav className="border-b border-stone-300 bg-white">
        <div className="max-w-7xl mx-auto px-6 flex gap-8">
          {[
            { id: 'overview', label: '戦略概要' },
            { id: 'backtest', label: 'バックテスト' },
            { id: 'screener', label: 'スクリーナー' },
            { id: 'trades', label: 'トレード履歴' },
          ].map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`py-4 text-sm tracking-wide transition-colors border-b-2 ${
                activeTab === t.id ? 'border-stone-900 font-semibold' : 'border-transparent text-stone-500 hover:text-stone-900'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === 'overview' && (
          <div className="space-y-8">
            <div className="grid md:grid-cols-2 gap-6">
              <div className="bg-white border border-stone-300 p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Activity size={18} />
                  <h3 className="font-semibold tracking-wide">戦略コンセプト</h3>
                </div>
                <p className="text-sm leading-relaxed text-stone-700">
                  出来高ブレイクで <strong>強い銘柄を機械的に抽出</strong>し、その後の押し目で <strong>波乗りタイミングを取る</strong>ハイブリッド戦略。
                  cleartrade の銘柄選定 × 波乗りのエントリー精度を統合。
                </p>
              </div>
              <div className="bg-white border border-stone-300 p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Target size={18} />
                  <h3 className="font-semibold tracking-wide">期待水準</h3>
                </div>
                <div className="text-sm space-y-1.5 text-stone-700">
                  <div className="flex justify-between"><span>勝率</span><span className="font-mono">50–60%</span></div>
                  <div className="flex justify-between"><span>リスクリワード</span><span className="font-mono">1.5–2.0</span></div>
                  <div className="flex justify-between"><span>プロフィットファクター</span><span className="font-mono">1.2–1.6</span></div>
                  <div className="flex justify-between"><span>年率リターン</span><span className="font-mono">+10〜25%</span></div>
                </div>
              </div>
            </div>

            <div className="bg-white border border-stone-300">
              <div className="border-b border-stone-300 px-6 py-3">
                <h3 className="font-semibold tracking-wide text-sm">確定済みルール一覧</h3>
              </div>
              <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-stone-300">
                <div className="p-6 space-y-4">
                  <RuleSection
                    icon={<ChevronRight size={14} />}
                    title="① スクリーニング (cleartrade層)"
                    items={[
                      "出来高 ≥ 20日平均 × 2.0",
                      "終値 ≥ 20日高値",
                      "20日リターン ≥ +5%",
                    ]}
                  />
                  <RuleSection
                    icon={<ChevronRight size={14} />}
                    title="② トレンドフィルター"
                    items={[
                      "銘柄終値 > 20日移動平均",
                      "TOPIX終値 > 20日移動平均",
                    ]}
                  />
                  <RuleSection
                    icon={<ChevronRight size={14} />}
                    title="③ 押し目検出 (波乗り層)"
                    items={[
                      "10日高値から -5% 〜 -3%",
                      "5日平均出来高 < 直近ピーク日の70%",
                      "終値 ≥ 20日線",
                      "※直近ピーク日 = 出来高最大かつ価格高値日",
                    ]}
                  />
                </div>
                <div className="p-6 space-y-4">
                  <RuleSection
                    icon={<Zap size={14} />}
                    title="④ エントリートリガー"
                    items={[
                      "前日高値を上抜け、または",
                      "陽線包み足の発生",
                    ]}
                  />
                  <RuleSection
                    icon={<Shield size={14} />}
                    title="⑤ エグジット"
                    items={[
                      "損切り: -5% (固定)",
                      "TP1: +10%で50%利確",
                      "TP1後: 5日線 or 建値の高い方をストップ",
                    ]}
                  />
                  <RuleSection
                    icon={<AlertCircle size={14} />}
                    title="⑥ 除外ルール"
                    items={[
                      "決算3営業日以内",
                      "ギャップアップ +5% 以上",
                      "陰線かつ出来高増加",
                    ]}
                  />
                </div>
              </div>
            </div>

            <div className="bg-stone-900 text-stone-50 p-6">
              <h3 className="font-semibold tracking-wide text-sm mb-3">推奨実装スタック (本番運用時)</h3>
              <div className="grid md:grid-cols-3 gap-4 text-sm">
                <div>
                  <div className="text-stone-400 text-xs uppercase tracking-wider mb-1">データソース</div>
                  <div>J-Quants API (公式)</div>
                  <div className="text-xs text-stone-400 mt-1">無料プランで12週遅延データ。バックテストには十分。</div>
                </div>
                <div>
                  <div className="text-stone-400 text-xs uppercase tracking-wider mb-1">バックエンド</div>
                  <div>Python (pandas + backtesting.py)</div>
                  <div className="text-xs text-stone-400 mt-1">毎晩データ取得→スクリーナー実行→結果保存。</div>
                </div>
                <div>
                  <div className="text-stone-400 text-xs uppercase tracking-wider mb-1">フロントエンド</div>
                  <div>Streamlit ダッシュボード</div>
                  <div className="text-xs text-stone-400 mt-1">ブラウザでバックテスト結果と日次候補を確認。</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'backtest' && (
          <div className="space-y-6">
            <div className="bg-white border border-stone-300 p-6">
              <h3 className="font-semibold tracking-wide text-sm mb-4">バックテスト設定</h3>
              <div className="grid md:grid-cols-3 gap-6">
                <div>
                  <label className="block text-xs text-stone-600 mb-2 tracking-wide">初期資金</label>
                  <input
                    type="number"
                    value={initialCapital}
                    onChange={e => setInitialCapital(Number(e.target.value))}
                    className="w-full border border-stone-300 px-3 py-2 text-sm font-mono focus:outline-none focus:border-stone-900"
                  />
                  <div className="text-xs text-stone-500 mt-1 font-mono">
                    {(initialCapital / 100000000).toFixed(2)} 億円
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-stone-600 mb-2 tracking-wide">
                    1トレードリスク: {riskPerTrade.toFixed(2)}%
                  </label>
                  <input
                    type="range"
                    min="0.10"
                    max="0.25"
                    step="0.01"
                    value={riskPerTrade}
                    onChange={e => setRiskPerTrade(Number(e.target.value))}
                    className="w-full"
                  />
                  <div className="text-xs text-stone-500 mt-1 font-mono">
                    1トレード許容損失: {(initialCapital * riskPerTrade / 100).toLocaleString()} 円
                  </div>
                </div>
                <div className="flex items-end gap-2">
                  <button
                    onClick={() => setHasRun(true)}
                    className="px-6 py-2 bg-stone-900 text-stone-50 text-sm tracking-wide hover:bg-stone-700 flex items-center gap-2"
                  >
                    <Play size={14} /> 実行
                  </button>
                  <button
                    onClick={() => setHasRun(false)}
                    className="px-4 py-2 border border-stone-300 text-sm hover:bg-stone-100 flex items-center gap-2"
                  >
                    <RotateCcw size={14} />
                  </button>
                </div>
              </div>
              <p className="text-xs text-stone-500 mt-4">
                ※サンプルデータ（6銘柄 × 750日）でロジック検証用。本番は J-Quants API のデータで実行してください。
              </p>
            </div>

            {stats && (
              <>
                <div className="grid md:grid-cols-4 gap-4">
                  <StatCard label="総リターン" value={`${stats.totalReturn >= 0 ? '+' : ''}${stats.totalReturn.toFixed(1)}%`} positive={stats.totalReturn > 0} />
                  <StatCard label="年率リターン" value={`${stats.annualReturn >= 0 ? '+' : ''}${stats.annualReturn.toFixed(1)}%`} positive={stats.annualReturn > 0} />
                  <StatCard label="最大DD" value={`-${stats.maxDD.toFixed(1)}%`} positive={false} />
                  <StatCard label="トレード数" value={stats.tradeCount} />
                </div>

                <div className="grid md:grid-cols-3 gap-4">
                  <StatCard label="勝率" value={`${stats.winRate.toFixed(1)}%`} positive={stats.winRate >= 50} />
                  <StatCard label="リスクリワード" value={stats.rr.toFixed(2)} positive={stats.rr >= 1.5} />
                  <StatCard label="プロフィットファクター" value={stats.pf.toFixed(2)} positive={stats.pf >= 1.2} />
                </div>

                <div className="bg-white border border-stone-300 p-6">
                  <h3 className="font-semibold tracking-wide text-sm mb-4">エクイティカーブ (百万円)</h3>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={equityChartData}>
                      <CartesianGrid strokeDasharray="2 4" stroke="#d6d3d1" />
                      <XAxis dataKey="day" stroke="#78716c" fontSize={11} />
                      <YAxis stroke="#78716c" fontSize={11} />
                      <Tooltip contentStyle={{ background: '#fafaf9', border: '1px solid #44403c', fontSize: 12 }} />
                      <ReferenceLine y={initialCapital / 1000000} stroke="#a8a29e" strokeDasharray="3 3" label={{ value: '初期資金', fontSize: 10, fill: '#78716c' }} />
                      <Line type="monotone" dataKey="value" stroke="#1c1917" strokeWidth={1.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <div className="bg-white border border-stone-300 p-6">
                  <h3 className="font-semibold tracking-wide text-sm mb-4">月次リターン分布 (%)</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={monthlyReturns}>
                      <CartesianGrid strokeDasharray="2 4" stroke="#d6d3d1" />
                      <XAxis dataKey="month" stroke="#78716c" fontSize={10} />
                      <YAxis stroke="#78716c" fontSize={11} />
                      <Tooltip contentStyle={{ background: '#fafaf9', border: '1px solid #44403c', fontSize: 12 }} />
                      <ReferenceLine y={0} stroke="#44403c" />
                      <Bar dataKey="ret" fill="#1c1917" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}

            {!hasRun && (
              <div className="bg-stone-100 border border-stone-300 p-12 text-center">
                <Activity size={32} className="mx-auto mb-3 text-stone-400" />
                <p className="text-sm text-stone-600">設定を確認して「実行」を押してください</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'screener' && (
          <DailyScreener allStockData={allStockData} topixData={topixData} />
        )}

        {activeTab === 'trades' && (
          <TradeHistory result={result} hasRun={hasRun} />
        )}
      </main>

      <footer className="border-t border-stone-300 bg-white mt-16">
        <div className="max-w-7xl mx-auto px-6 py-6 text-xs text-stone-500 tracking-wide">
          検証用シミュレーター / 内蔵サンプルデータでのロジック動作確認用 / 本番運用は別途データ接続が必要
        </div>
      </footer>
    </div>
  );
}

function RuleSection({ icon, title, items }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <h4 className="text-sm font-semibold tracking-wide">{title}</h4>
      </div>
      <ul className="text-xs text-stone-700 space-y-1 ml-5 list-disc">
        {items.map((item, i) => <li key={i}>{item}</li>)}
      </ul>
    </div>
  );
}

function StatCard({ label, value, positive }) {
  const colorClass = positive === undefined ? 'text-stone-900' : positive ? 'text-emerald-700' : 'text-red-700';
  return (
    <div className="bg-white border border-stone-300 p-4">
      <div className="text-xs text-stone-600 tracking-wide uppercase mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${colorClass}`}>{value}</div>
    </div>
  );
}

function DailyScreener({ allStockData, topixData }) {
  const lastDay = topixData.length - 1;
  const candidates = useMemo(() => {
    const results = [];
    Object.entries(allStockData).forEach(([code, data]) => {
      const sigs = detectSignals(data, topixData);
      // 直近30日以内のシグナルを抽出
      sigs.filter(s => s.idx >= lastDay - 30).forEach(s => {
        const config = stockConfigs.find(c => c.code === code);
        results.push({ ...s, code, name: config?.name || code });
      });
    });
    return results.sort((a, b) => b.signalScore - a.signalScore);
  }, [allStockData, topixData, lastDay]);

  return (
    <div className="space-y-6">
      <div className="bg-white border border-stone-300 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold tracking-wide text-sm">直近30日のシグナル候補</h3>
          <span className="text-xs text-stone-500 font-mono">{candidates.length} 件</span>
        </div>
        {candidates.length === 0 ? (
          <p className="text-sm text-stone-500 text-center py-8">直近30日にシグナル発生なし</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b-2 border-stone-300">
                <tr className="text-left text-xs text-stone-600 uppercase tracking-wide">
                  <th className="py-2 pr-4">日付</th>
                  <th className="py-2 pr-4">銘柄</th>
                  <th className="py-2 pr-4">エントリー</th>
                  <th className="py-2 pr-4 text-right">出来高倍率</th>
                  <th className="py-2 pr-4 text-right">20日リターン</th>
                  <th className="py-2 pr-4 text-right">押し目幅</th>
                  <th className="py-2 pr-4">トリガー</th>
                  <th className="py-2 text-right">スコア</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c, i) => (
                  <tr key={i} className="border-b border-stone-200 hover:bg-stone-50">
                    <td className="py-3 pr-4 font-mono text-xs">{c.date}</td>
                    <td className="py-3 pr-4">
                      <div className="font-mono text-xs">{c.code}</div>
                      <div className="text-xs text-stone-500">{c.name}</div>
                    </td>
                    <td className="py-3 pr-4 font-mono">¥{c.entryPrice.toLocaleString()}</td>
                    <td className="py-3 pr-4 text-right font-mono">{c.volRatio.toFixed(2)}x</td>
                    <td className="py-3 pr-4 text-right font-mono">{(c.ret20 * 100).toFixed(1)}%</td>
                    <td className="py-3 pr-4 text-right font-mono text-red-700">{(c.dipPct * 100).toFixed(1)}%</td>
                    <td className="py-3 pr-4">
                      <span className="text-xs px-2 py-0.5 bg-stone-200 rounded">{c.triggerType}</span>
                    </td>
                    <td className="py-3 text-right font-mono font-bold">{c.signalScore.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="bg-stone-100 border border-stone-300 p-4">
        <p className="text-xs text-stone-600 leading-relaxed">
          <strong>シグナル強度スコア</strong> = 0.4×(出来高倍率-2.0) + 0.3×(20日リターン-0.05)×10 + 0.3×(1-|押し目幅+0.04|/0.01)
          <br />押し目幅は -4% が最高スコア。出来高倍率と20日リターンが大きいほど高スコア。
        </p>
      </div>
    </div>
  );
}

function TradeHistory({ result, hasRun }) {
  if (!hasRun || !result) {
    return (
      <div className="bg-stone-100 border border-stone-300 p-12 text-center">
        <p className="text-sm text-stone-600">先にバックテストを実行してください</p>
      </div>
    );
  }

  const closedTrades = result.trades.filter(t => t.pnl !== undefined).slice(-50).reverse();

  return (
    <div className="bg-white border border-stone-300 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold tracking-wide text-sm">トレード履歴 (直近50件)</h3>
        <span className="text-xs text-stone-500 font-mono">全{result.trades.filter(t => t.pnl !== undefined).length}件中</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b-2 border-stone-300">
            <tr className="text-left text-xs text-stone-600 uppercase tracking-wide">
              <th className="py-2 pr-4">エントリー日</th>
              <th className="py-2 pr-4">銘柄</th>
              <th className="py-2 pr-4 text-right">建値</th>
              <th className="py-2 pr-4 text-right">手仕舞い</th>
              <th className="py-2 pr-4 text-right">株数</th>
              <th className="py-2 pr-4 text-right">P&L</th>
              <th className="py-2 pr-4 text-right">%</th>
              <th className="py-2">理由</th>
            </tr>
          </thead>
          <tbody>
            {closedTrades.map((t, i) => (
              <tr key={i} className="border-b border-stone-200 hover:bg-stone-50">
                <td className="py-2 pr-4 font-mono text-xs">{t.entryDate}</td>
                <td className="py-2 pr-4 font-mono text-xs">{t.code}</td>
                <td className="py-2 pr-4 text-right font-mono">¥{t.entryPrice.toLocaleString()}</td>
                <td className="py-2 pr-4 text-right font-mono">¥{t.exitPrice.toLocaleString()}</td>
                <td className="py-2 pr-4 text-right font-mono text-xs">{t.shares.toLocaleString()}</td>
                <td className={`py-2 pr-4 text-right font-mono ${t.pnl >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                  {t.pnl >= 0 ? '+' : ''}{Math.round(t.pnl).toLocaleString()}
                </td>
                <td className={`py-2 pr-4 text-right font-mono ${t.pnlPct >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                  {t.pnlPct >= 0 ? '+' : ''}{(t.pnlPct * 100).toFixed(1)}%
                </td>
                <td className="py-2">
                  <span className="text-xs px-2 py-0.5 bg-stone-200 rounded">{t.exitReason}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
