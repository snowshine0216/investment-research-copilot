# Phase D look-through diff report (gate #5)

注意：本估值为「当前持仓 × 历史个股 PE」构造的 current-basket 序列，并非基金真实历史 PE（不存历史持仓）。

## Per-fund flip & coverage
| id | 名称 | NAV band | PE band | flip | Δpct | PE cov | PE src | PB cov | PB src |
|---|---|---|---|---|---|---|---|---|---|
| 000127 | 农银行业领先混合 | expensive | cheap | YES | -0.80 | 0.53 | eastmoney | 0.53 | eastmoney |
| 000390 | 华商优势行业混合A | very_expensive | — | no | — | 0.47 | eastmoney | 0.47 | eastmoney |
| 000452 | 南方医药保健灵活配置混合A | fair | — | no | — | 0.52 | eastmoney | 0.52 | eastmoney |
| 000531 | 东吴阿尔法灵活配置混合A | very_expensive | very_expensive | no | -0.00 | 0.73 | eastmoney | 0.73 | eastmoney |
| 000845 | 国投瑞银信息消费混合A | very_expensive | very_expensive | no | +0.00 | 0.61 | eastmoney | 0.61 | eastmoney |
| 001008 | 工银国企改革股票 | very_expensive | fair | YES | -0.45 | 0.60 | eastmoney | 0.60 | eastmoney |
| 001054 | 工银新金融股票A | very_expensive | cheap | YES | -0.85 | 0.61 | eastmoney | 0.61 | eastmoney |
| 001069 | 华泰柏瑞消费成长混合 | very_expensive | expensive | YES | -0.08 | 0.53 | eastmoney | 0.53 | eastmoney |
| 001075 | 宝盈转型动力混合A | very_expensive | very_expensive | no | -0.00 | 0.54 | eastmoney | 0.54 | eastmoney |
| 001076 | 易方达改革红利混合 | very_expensive | — | no | — | 0.32 | eastmoney | 0.32 | eastmoney |
| 001158 | 工银新材料新能源股票 | very_expensive | — | no | — | 0.40 | eastmoney | 0.40 | eastmoney |
| 001184 | 易方达新常态灵活配置混合 | very_expensive | very_expensive | no | +0.00 | 0.55 | eastmoney | 0.55 | eastmoney |
| 001188 | 鹏华改革红利股票 | very_expensive | — | no | — | 0.44 | eastmoney | 0.48 | eastmoney |
| 001194 | 景顺长城稳健回报混合A | very_expensive | very_expensive | no | +0.00 | 0.61 | eastmoney | 0.61 | eastmoney |
| 001230 | 鹏华医药科技股票A | very_expensive | — | no | — | 0.32 | eastmoney | 0.51 | eastmoney |
| 001277 | 博时国企改革股票A | expensive | — | no | — | 0.40 | eastmoney | 0.40 | eastmoney |
| 001490 | 汇添富国企创新股票A | expensive | — | no | — | 0.41 | eastmoney | 0.41 | eastmoney |
| 001558 | 天弘医疗健康混合A | expensive | fair | YES | -0.28 | 0.67 | eastmoney | 0.67 | eastmoney |
| 001574 | 中海混改红利混合A | fair | fair | no | -0.19 | 0.56 | eastmoney | 0.56 | eastmoney |
| 001877 | 宝盈国家安全沪港深股票A | very_expensive | — | no | — | 0.49 | eastmoney | 0.49 | eastmoney |
| 002258 | 大成国企改革灵活配置混合A | very_expensive | reasonable_low | YES | -0.65 | 0.64 | eastmoney | 0.64 | eastmoney |
| 003304 | 前海开源沪港深核心资源混合A | very_expensive | fair | YES | -0.35 | 0.59 | eastmoney | 0.59 | eastmoney |
| 003318 | 景顺长城中证500行业中性低波动指数A | very_expensive | — | no | — | 0.12 | eastmoney | 0.12 | eastmoney |
| 003396 | 东方红优享红利混合A | very_expensive | — | no | — | 0.32 | eastmoney | 0.32 | eastmoney |
| 003624 | 创金合信资源股票发起式A | very_expensive | — | no | — | 0.48 | eastmoney | 0.48 | eastmoney |
| 004224 | 南方军工改革灵活配置混合A | expensive | — | no | — | 0.39 | eastmoney | 0.39 | eastmoney |
| 004814 | 中欧红利优享混合A | very_expensive | — | no | — | 0.17 | eastmoney | 0.17 | eastmoney |
| 005270 | 太平改革红利精选混合 | very_expensive | fair | YES | -0.39 | 0.66 | eastmoney | 0.66 | eastmoney |
| 005303 | 嘉实医药健康股票A | fair | — | no | — | 0.51 | eastmoney | 0.51 | eastmoney |
| 005660 | 嘉实资源精选股票A | very_expensive | fair | YES | -0.47 | 0.55 | eastmoney | 0.55 | eastmoney |
| 005825 | 申万菱信智能驱动股票A | very_expensive | very_expensive | no | -0.00 | 0.68 | eastmoney | 0.68 | eastmoney |
| 005827 | 易方达蓝筹精选 | reasonable_low | — | no | — | 0.43 | eastmoney | 0.43 | eastmoney |
| 005937 | 工银精选金融地产混合A | very_expensive | — | no | — | 0.45 | eastmoney | 0.45 | eastmoney |
| 005939 | 工银新能源汽车混合A | very_expensive | — | no | — | 0.46 | eastmoney | 0.46 | eastmoney |
| 006751 | 富国互联科技股票A | very_expensive | very_expensive | no | +0.00 | 0.55 | eastmoney | 0.55 | eastmoney |
| 006809 | 泰康香港银行指数A | very_expensive | — | no | — | 0.00 | — | 0.00 | — |
| 008177 | 建信高股息主题股票 | expensive | fair | YES | -0.11 | 0.52 | eastmoney | 0.52 | eastmoney |
| 008359 | 华安医疗创新混合A | reasonable_low | — | no | — | 0.24 | eastmoney | 0.24 | eastmoney |
| 008382 | 融通产业趋势股票 | very_expensive | very_expensive | no | -0.00 | 0.61 | eastmoney | 0.61 | eastmoney |
| 008555 | 华商龙头优势混合 | very_expensive | — | no | — | 0.53 | eastmoney | 0.53 | eastmoney |
| 008934 | 大成科技消费股票A | very_expensive | — | no | — | 0.33 | eastmoney | 0.33 | eastmoney |
| 008988 | 大成科技创新混合A | very_expensive | very_expensive | no | -0.01 | 0.57 | eastmoney | 0.57 | eastmoney |
| 009500 | 国寿安保高股息混合A | very_expensive | — | no | — | 0.40 | eastmoney | 0.40 | eastmoney |
| 010421 | 海富通消费优选混合A | very_expensive | — | no | — | 0.43 | eastmoney | 0.43 | eastmoney |
| 010731 | 广发创新医疗两年持有混合A | expensive | — | no | — | 0.41 | eastmoney | 0.41 | eastmoney |
| 011466 | 兴业医疗保健混合A | reasonable_low | cheap | YES | -0.37 | 0.53 | eastmoney | 0.53 | eastmoney |
| 012445 | 华富新能源股票型发起式A | very_expensive | — | no | — | 0.42 | eastmoney | 0.42 | eastmoney |
| 012578 | 富国红利混合A | very_expensive | — | no | — | 0.41 | eastmoney | 0.41 | eastmoney |
| 013369 | 汇添富自主核心科技一年持有混合A | very_expensive | very_expensive | no | +0.00 | 0.58 | eastmoney | 0.58 | eastmoney |
| 013942 | 华宝中证稀有金属指数增强发起A | very_expensive | fair | YES | -0.35 | 0.55 | eastmoney | 0.55 | eastmoney |
| 014193 | 汇添富中证芯片产业指数增强发起式A | very_expensive | very_expensive | no | -0.00 | 0.70 | eastmoney | 0.70 | eastmoney |
| 014466 | 工银行业优选混合A | expensive | — | no | — | 0.29 | eastmoney | 0.29 | eastmoney |
| 014611 | 富国核心科技12个月持有混合A | very_expensive | very_expensive | no | +0.00 | 0.55 | eastmoney | 0.55 | eastmoney |
| 015904 | 广发新能源精选股票A | very_expensive | — | no | — | 0.46 | eastmoney | 0.46 | eastmoney |
| 015915 | 永赢医药创新智选混合发起A | expensive | — | no | — | 0.36 | eastmoney | 0.41 | eastmoney |
| 017876 | 汇添富新能源精选混合发起式A | very_expensive | — | no | — | 0.49 | eastmoney | 0.49 | eastmoney |
| 017987 | 易方达国企主题混合A | very_expensive | fair | YES | -0.31 | 0.54 | eastmoney | 0.54 | eastmoney |
| 018132 | 博时中证有色金属矿业主题指数A | expensive | — | no | — | 0.49 | eastmoney | 0.49 | eastmoney |
| 018294 | 景顺长城国企价值混合A | expensive | — | no | — | 0.30 | eastmoney | 0.30 | eastmoney |
| 018956 | 中航机遇领航混合发起A | very_expensive | very_expensive | no | -0.00 | 0.73 | eastmoney | 0.73 | eastmoney |
| 019589 | 东财中证化工指数发起式A | expensive | — | no | — | 0.44 | eastmoney | 0.44 | eastmoney |
| 019829 | 华夏数字产业混合A | very_expensive | very_expensive | no | +0.00 | 0.60 | eastmoney | 0.60 | eastmoney |
| 020397 | 中银港股通医药混合发起A | fair | — | no | — | 0.00 | — | 0.00 | — |
| 020691 | 博时中证全指通信设备指数发起式A | very_expensive | very_expensive | no | +0.00 | 0.65 | eastmoney | 0.65 | eastmoney |
| 020899 | 天弘中证全指通信设备指数发起A | very_expensive | very_expensive | no | +0.00 | 0.66 | eastmoney | 0.66 | eastmoney |
| 021642 | 富国资源精选混合发起式A | very_expensive | fair | YES | -0.24 | 0.69 | eastmoney | 0.69 | eastmoney |
| 021875 | 路博迈资源精选股票发起A | expensive | — | no | — | 0.29 | eastmoney | 0.29 | eastmoney |
| 021977 | 中欧中证细分化工产业主题指数发起A | expensive | — | no | — | 0.44 | eastmoney | 0.44 | eastmoney |
| 021988 | 银河中证通信设备主题指数发起式A | very_expensive | very_expensive | no | +0.00 | 0.59 | eastmoney | 0.59 | eastmoney |
| 023036 | 中欧资源精选混合发起A | expensive | — | no | — | 0.42 | eastmoney | 0.42 | eastmoney |
| 023448 | 上银资源精选混合发起式A | expensive | — | no | — | 0.19 | eastmoney | 0.19 | eastmoney |
| 023451 | 中欧信息科技混合发起A | very_expensive | — | no | — | 0.49 | eastmoney | 0.49 | eastmoney |
| 110022 | 易方达消费行业 | fair | cheap | YES | -0.53 | 0.67 | eastmoney | 0.67 | eastmoney |
| 110025 | 易方达资源行业混合 | very_expensive | — | no | — | 0.49 | eastmoney | 0.49 | eastmoney |
| 160221 | 国泰国证有色金属行业指数(LOF)A | very_expensive | — | no | — | 0.46 | eastmoney | 0.46 | eastmoney |
| 160620 | 鹏华中证A股资源产业指数(LOF)A | very_expensive | — | no | — | 0.25 | eastmoney | 0.25 | eastmoney |
| 160624 | 鹏华消费领先混合 | expensive | — | no | — | 0.43 | eastmoney | 0.43 | eastmoney |
| 161005 | 富国天惠成长LOF | very_expensive | — | no | — | 0.37 | eastmoney | 0.37 | eastmoney |
| 161024 | 富国中证军工指数(LOF)A | expensive | — | no | — | 0.33 | eastmoney | 0.33 | eastmoney |
| 161217 | 国投瑞银中证资源指数(LOF)A | very_expensive | — | no | — | 0.46 | eastmoney | 0.46 | eastmoney |
| 163115 | 申万菱信中证军工指数(LOF)A | expensive | — | no | — | 0.33 | eastmoney | 0.33 | eastmoney |
| 163417 | 兴全合宜A | very_expensive | — | no | — | 0.26 | eastmoney | 0.26 | eastmoney |
| 164402 | 前海开源中航军工指数A | fair | reasonable_low | YES | -0.28 | 0.56 | eastmoney | 0.56 | eastmoney |
| 165520 | 中信保诚中证800有色指数(LOF)A | very_expensive | — | no | — | 0.49 | eastmoney | 0.49 | eastmoney |
| 202009 | 南方盛元红利混合 | expensive | — | no | — | 0.33 | eastmoney | 0.33 | eastmoney |
| 213008 | 宝盈资源优选混合 | very_expensive | very_expensive | no | +0.01 | 0.61 | eastmoney | 0.61 | eastmoney |
| 240022 | 华宝资源优选混合A | very_expensive | fair | YES | -0.46 | 0.56 | eastmoney | 0.56 | eastmoney |
| 481006 | 工银红利混合 | expensive | — | no | — | 0.48 | eastmoney | 0.48 | eastmoney |
| 501019 | 国泰国证航天军工指数(LOF)A | expensive | — | no | — | 0.44 | eastmoney | 0.44 | eastmoney |
| 501025 | 鹏华中证香港银行指数(LOF)A | very_expensive | — | no | — | 0.00 | — | 0.00 | — |
| 519002 | 华安安信消费混合A | very_expensive | — | no | — | 0.43 | eastmoney | 0.43 | eastmoney |
| 519091 | 新华泛资源优势混合 | very_expensive | — | no | — | 0.42 | eastmoney | 0.42 | eastmoney |
| 519770 | 交银优择回报灵活配置混合A | very_expensive | very_expensive | no | +0.00 | 0.54 | eastmoney | 0.54 | eastmoney |
| 660001 | 农银行业成长混合 | very_expensive | — | no | — | 0.27 | eastmoney | 0.27 | eastmoney |
| 690008 | 民生中证内地资源主题指数A | very_expensive | — | no | — | 0.45 | eastmoney | 0.45 | eastmoney |

## Coverage-floor sensitivity (grounded funds)

| floor | grounded funds |
|---|---|
| 0.40 | 71 |
| 0.50 | 40 |
| 0.60 | 17 |
