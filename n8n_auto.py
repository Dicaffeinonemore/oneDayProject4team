{
  "name": "4조 소비패턴 브리핑 메일",
  "nodes": [
    {
      "parameters": {
        "content": "## 4조 소비패턴 브리핑 메일 (6번 이성호)\n\n**흐름**: 수동 실행 → GitHub의 output/brief.json 가져오기 → Gmail로 브리핑 발송\n\n**brief.json**: function/brief_seongho.py가 거래 1,200건에서 핵심 지표 5개를 계산해 만든 파일 (subject, body, kpis)\n\n**실행 전 설정**\n1. 'brief.json 가져오기' URL이 막히면 jsDelivr 주소로 교체\n   https://cdn.jsdelivr.net/gh/Dicaffeinonemore/oneDayProject4team@main/output/brief.json\n2. '브리핑 메일 발송' 노드에 본인 Gmail 계정(OAuth2) 연결\n3. To 칸에 받는 사람 주소 입력\n\n**참고**: 강의실 네트워크에서 Docker n8n의 외부 연결이 차단되어, 시연은 brief.json 내용을 Code 노드에 넣은 오프라인 버전으로 진행함 (Google 인증·Gmail 서버 연결까지 확인)",
        "height": 420,
        "width": 520,
        "color": 5
      },
      "name": "설명 메모",
      "type": "n8n-nodes-base.stickyNote",
      "typeVersion": 1,
      "position": [
        -60,
        -480
      ]
    },
    {
      "parameters": {},
      "name": "When clicking 'Execute workflow'",
      "type": "n8n-nodes-base.manualTrigger",
      "typeVersion": 1,
      "position": [
        0,
        0
      ]
    },
    {
      "parameters": {
        "url": "https://raw.githubusercontent.com/Dicaffeinonemore/oneDayProject4team/main/output/brief.json",
        "options": {
          "response": {
            "response": {
              "responseFormat": "json"
            }
          }
        }
      },
      "name": "brief.json 가져오기",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [
        260,
        0
      ]
    },
    {
      "parameters": {
        "sendTo": "your-email@example.com",
        "subject": "={{ $json.subject }}",
        "emailType": "text",
        "message": "={{ $json.body }}",
        "options": {}
      },
      "name": "브리핑 메일 발송",
      "type": "n8n-nodes-base.gmail",
      "typeVersion": 2.1,
      "position": [
        520,
        0
      ]
    }
  ],
  "connections": {
    "When clicking 'Execute workflow'": {
      "main": [
        [
          {
            "node": "brief.json 가져오기",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "brief.json 가져오기": {
      "main": [
        [
          {
            "node": "브리핑 메일 발송",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "settings": {}
}