from collections.abc import Sequence

from app.schemas.feed import FeedArticle
from app.schemas.topic import TopicCandidate, TopicClusteringOutput
from app.services.llm import StructuredLLM

AGENT = "trend"
MAX_INPUT_ARTICLES = 80
SUMMARY_CHARS = 120
MAX_CANDIDATES = 5

SYSTEM_PROMPT = """당신은 경제 카드뉴스 계정의 편집자입니다.
최근 경제 기사 목록을 받아, 같은 사건이나 같은 경제 지표를 다룬 기사끼리 묶어 카드뉴스 주제 후보를 만듭니다.

- article_ids에는 입력 목록에 있는 ID만 그대로 씁니다.
- 경제와 관련이 약한 기사(연예, 스포츠, 일반 사건사고, 단순 상품 홍보)는 어느 묶음에도 넣지 않습니다.
- 한 기사만 다룬 주제도 후보가 될 수 있습니다.
- keywords에는 한국은행 보도자료 제목이나 본문에 나올 만한 경제 용어를 2~5개 씁니다. 예: 기준금리, 가계대출, 소비자물가, 경상수지, 환율, 경제심리지수.
- reason에는 독자에게 이 주제가 왜 중요한지 한 문장으로 씁니다."""


def _article_line(article: FeedArticle) -> str:
    summary = " ".join(article.summary.split())[:SUMMARY_CHARS]
    return f"{article.article_id} | {article.publisher} | {article.title} | {summary}"


def build_prompt(articles: Sequence[FeedArticle]) -> str:
    lines = "\n".join(_article_line(article) for article in articles)
    return f"기사 목록 (ID | 매체 | 제목 | 요약 일부)\n{lines}"


def rank_candidates(
    output: TopicClusteringOutput, articles: Sequence[FeedArticle]
) -> list[TopicCandidate]:
    """LLM이 만든 묶음을 검사하고, 다룬 매체 수 → 기사 수 → 최신순으로 정렬한다.

    순위는 코드가 정한다. LLM이 없는 ID를 만들면 그 ID는 버린다.
    """
    by_id = {article.article_id: article for article in articles}
    drafts = []
    for cluster in output.clusters:
        article_ids = tuple(dict.fromkeys(i for i in cluster.article_ids if i in by_id))
        keywords = tuple(dict.fromkeys(k.strip() for k in cluster.keywords if k.strip()))
        if not article_ids or not keywords or not cluster.topic.strip():
            continue
        cluster_articles = [by_id[i] for i in article_ids]
        drafts.append((cluster, article_ids, keywords, cluster_articles))

    drafts.sort(
        key=lambda draft: (
            len({article.publisher for article in draft[3]}),
            len(draft[1]),
            max(article.published_at for article in draft[3]),
        ),
        reverse=True,
    )
    return [
        TopicCandidate(
            candidate_id=f"topic-{rank}",
            topic=cluster.topic,
            article_ids=article_ids,
            publishers=tuple(dict.fromkeys(article.publisher for article in cluster_articles)),
            reason=cluster.reason.strip() or cluster.topic,
            keywords=keywords,
            latest_published_at=max(article.published_at for article in cluster_articles),
        )
        for rank, (cluster, article_ids, keywords, cluster_articles) in enumerate(
            drafts[:MAX_CANDIDATES], start=1
        )
    ]


async def find_topic_candidates(
    llm: StructuredLLM, articles: Sequence[FeedArticle]
) -> list[TopicCandidate]:
    """뉴스 기사로 주제 후보를 만든다. 기사가 없으면 LLM을 부르지 않는다."""
    recent = sorted(articles, key=lambda article: article.published_at, reverse=True)
    recent = recent[:MAX_INPUT_ARTICLES]
    if not recent:
        return []

    output = await llm.parse(
        agent=AGENT,
        system=SYSTEM_PROMPT,
        prompt=build_prompt(recent),
        output_type=TopicClusteringOutput,
    )
    return rank_candidates(output, recent)
