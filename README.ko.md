[中文](README.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

# 🧠 또 하나의 주식 앱이 아니라, 당신을 위한 AI 가치투자 분석 플랫폼

> @버핏 600519 분석 —— 한 줄이면 마스터 Agent가 자동으로 데이터를 가져오고, 6차원 건강 진단, 결론까지. 주식 앱은 수만 가지지만, 위대한 투자자를 채팅 창에 넣은 건 이것뿐.

<!-- 스크린샷 자리: 채팅 홈 + @마스터 + 밸류에이션 밴드
![Chat Home](docs/screenshots/chat-home.png)
![Value Analysis](docs/screenshots/value-analysis.png)
-->

## 🎯 왜 우리인가

세상의 주식 앱은 차가운 데이터 단말기이거나 차트만 그리는 뷰어가 대부분입니다. 우리가 하는 건 "시장 보기"가 아니라, **AI가 위대한 투자자처럼 생각하게 만드는 것**:

- **9명의 마스터 Agent가 채팅에 상주**: 버핏 / 찰리 멍거 / 피터 린치 / 소로스 / 탈렙 / 리버모어 / 그레이엄 / 피셔 + 현대 가치 분석 Agent —— 각자 철학 파일과 도구 보유
- **6차원 가치투자 프레임워크**: 밸류에이션 / 수익력 / 재무 안전성 / 현금흐름 / 성장성 / 배당 진위 —— 한 번에 종목의 완전한 가치 포르트레이트, 단순 PE만 보지 않습니다
- **대화형 인터페이스**: `@버핏 @그레이엄 600519 분석`으로 멀티 Agent 동시 협업, `/`로 전체 스킬 목록, 자연어로 백테스트 —— 메뉴 미로 없음

## ✨ 하이라이트

- 💬 **@마스터 + 자동 데이터 수집**: 메시지에 종목코드를 쓰면 플랫폼이 가치분석 데이터를 자동으로 가져와 LLM 컨텍스트에 주입. 마스터 Agent가 결론을 내리고, 도구가 대신 생각하지 않습니다
- 📊 **P/E P/B P/S 밸류에이션 밴드**: 퍼센타일 관점으로 저렴한지 판단, 절대수만 보는 건 끝
- 📈 **K선 전량 히스토리 + 주기 전환**: 2010년 이후 전체 데이터, 일/주/월/분기/년봉을 로컬에서 순식간에 전환 (pandas resample)
- 🏢 **통화순 크롤러로 회사 정보**: 실제 회사 개요 / 업종 / 섹터, LLM 날조 없음
- 🧪 **원클릭 백테스트**: 9개 전략 템플릿 + 자연어 파라미터 + 워크포워드 + 몬테카를로 신뢰구간
- 🐼 **순수 pandas 백테스팅 엔진**: vectorbt 등 무거운 의존성 없이, maverick-mcp (MIT)에서 이식, 가볍고 신뢰 가능
- 🌐 **중 / 영 / 일 / 한 4개 언어**: 가벼운 자체 i18n, localStorage에 영구 저장

## 🧭 더 할 수 있는 것들

- 💼 **포트폴리오 관리 + 리스크 대시보드**: VaR95/99, 업종 집중도, 거래 전 시뮬레이션, 레짐별 포지션 조정
- 🗣️ **멀티 Agent 디베이트**: 다른 스타일의 마스터들이 한 종목 / 한 포트폴리오에 대해 상호 비판, 응답, 요약
- 🎯 **설명 가능한 3전략 스크리닝**: bullish / bearish / supply_demand 스코어링, 블랙박스 작별
- 🔌 **Agent 도구 발견**: `GET /agent/tools`로 전체 엔드포인트 목록, `GET /agent/web-search`로 실시간 검색

## 🚀 3단계로 시작

```bash
# 백엔드
cd backend && uv sync
cp config.example.yaml config.yaml
export LLM_API_KEY=your-key
uv run uvicorn app.main:app --reload --port 8000

# 프론트엔드
cd frontend && npm install && npm run dev   # http://localhost:5173
```

프론트엔드를 열고, 채팅에 `@버핏 600519 분석`이라고 입력하세요. 당신의 가치투자 여정을 시작하세요.

<!-- 데모 GIF 자리 (추후 추가)
![Demo](docs/screenshots/demo.gif)
-->

## 📄 라이선스와 크레딧

플랫폼 코드는 자체 저작권. 백테스팅 / 시그널 / 스크리닝 / 리스크 모듈은 [maverick-mcp](https://github.com/wshobson/maverick-mcp) (MIT, Copyright (c) 2024)에서 이식, 파일 헤더에 표기. 데이터는 [akshare](https://github.com/akfamily/akshare) 제공.
