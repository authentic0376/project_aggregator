# project_aggregator
- 프로젝트의 디렉토리구조(트리)와 코드들을 output.txt에 모아준다
- chatGPT 등 ai에 직접 입력할 용도로 만듦
## 사용법
- path.yaml 을 만든다
  - path--*.yaml 은 무시된다. 저장용으로 사용
- path-template.yaml 을 참고 해서 작성
  ```bash
     poetry run scrape --config path.yaml --output output.txt
   ```