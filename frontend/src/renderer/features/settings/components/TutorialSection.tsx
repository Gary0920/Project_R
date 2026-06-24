import { useMemo, useState, type ReactNode } from "react";

import {
  BrainIcon,
  ChatIcon,
  ChevronRightIcon,
  NoteIcon,
  SearchIcon,
} from "../../../shared/icons/LineIcons";

type TutorialArticleId = "quick-start" | "employee-guide" | "query-guide" | "faq";

type TutorialArticle = {
  id: TutorialArticleId;
  title: string;
  summary: string;
  duration: string;
  icon: ReactNode;
  sections: Array<{
    title: string;
    body: React.ReactNode;
  }>;
};

const QUICK_QUERY = "/query 书面化原则是什么";

export function TutorialSection() {
  const [activeId, setActiveId] = useState<TutorialArticleId>("quick-start");

  const articles = useMemo<TutorialArticle[]>(() => [
    {
      id: "quick-start",
      title: "快速入门",
      summary: "第一次打开软件时，按登录、普通 Chat、知识库搜索三步上手。",
      duration: "约 5 分钟",
      icon: <NoteIcon />,
      sections: [
        {
          title: "1. 登录软件",
          body: (
            <ol>
              <li>打开 Project_R。</li>
              <li>如果出现服务器检测页，确认后端地址由管理员提供。</li>
              <li>检测通过后输入账号和密码登录。</li>
              <li>登录成功后进入聊天主界面。</li>
            </ol>
          ),
        },
        {
          title: "2. 发起一次普通 Chat",
          body: (
            <>
              <p>普通 Chat 适合写作、改写、解释、总结和轻量办公问答。</p>
              <div className="tutorial-example">请把这段客户回复改得更正式、更简洁：……</div>
            </>
          ),
        },
        {
          title: "3. 查一次知识库",
          body: (
            <>
              <p>需要查询公司制度、流程、标准或培训资料时，在问题前加 <code>/query</code>。</p>
              <div className="tutorial-example">{QUICK_QUERY}</div>
            </>
          ),
        },
      ],
    },
    {
      id: "employee-guide",
      title: "员工使用教程",
      summary: "日常使用中的会话管理、临时附件、提问方式和使用边界。",
      duration: "约 10 分钟",
      icon: <ChatIcon />,
      sections: [
        {
          title: "普通 Chat 适合什么",
          body: (
            <ul>
              <li>改写文字、起草邮件、总结材料。</li>
              <li>解释概念、整理思路、生成初稿。</li>
              <li>处理你在本轮对话中提供的上下文。</li>
            </ul>
          ),
        },
        {
          title: "会话怎么管理",
          body: (
            <ul>
              <li>一个主题使用一个会话，避免不同工作内容混在一起。</li>
              <li>重要会话可以重命名或置顶。</li>
              <li>暂时不用但想保留的会话可以归档，之后在设置中恢复。</li>
            </ul>
          ),
        },
        {
          title: "临时附件怎么理解",
          body: (
            <p>附件只服务当前对话。上传附件不等于进入知识库，也不会自动变成公司长期资料。</p>
          ),
        },
      ],
    },
    {
      id: "query-guide",
      title: "知识库搜索",
      summary: "什么时候用 /query，如何阅读带来源的回答。",
      duration: "约 6 分钟",
      icon: <SearchIcon />,
      sections: [
        {
          title: "什么时候使用 /query",
          body: (
            <ul>
              <li>查询公司流程、规则、标准和培训资料。</li>
              <li>需要回答带有来源，方便追溯。</li>
              <li>不确定普通 Chat 是否能可靠回答公司内部事实。</li>
            </ul>
          ),
        },
        {
          title: "如何阅读来源",
          body: (
            <ol>
              <li>先看结论是否直接回答问题。</li>
              <li>再看来源标题是否相关。</li>
              <li>最后看是否有资料缺口、冲突或警告提示。</li>
            </ol>
          ),
        },
        {
          title: "重要边界",
          body: (
            <p>普通 Chat 不会自动查询知识库。只有显式输入 <code>/query</code>，系统才会走知识库搜索入口。</p>
          ),
        },
      ],
    },
    {
      id: "faq",
      title: "常见问题",
      summary: "连接失败、登录失败、没有来源、AI 不回复时先看这里。",
      duration: "约 4 分钟",
      icon: <BrainIcon />,
      sections: [
        {
          title: "软件提示连接失败",
          body: <p>先确认电脑在公司内网，再联系管理员确认后端地址是否正确。</p>,
        },
        {
          title: "登录失败",
          body: <p>确认账号、密码和后端连接。不要反复猜密码，把错误提示反馈给管理员。</p>,
        },
        {
          title: "知识库回答没有来源",
          body: <p>先确认问题是否以 <code>/query</code> 开头。普通 Chat 不会自动查知识库。</p>,
        },
        {
          title: "AI 一直不回复",
          body: <p>记录时间、输入内容和错误提示，可能是模型服务或后端连接异常。</p>,
        },
      ],
    },
  ], []);

  const activeArticle = articles.find((article) => article.id === activeId) ?? articles[0];

  return (
    <div className="settings-section settings-tutorial-section">
      <div className="settings-section-header">
        <h3>软件教程</h3>
        <p>从日常对话开始，学习如何提问、整理内容，并用知识库搜索查找可信来源。</p>
      </div>

      <div className="tutorial-workspace">
        <aside className="tutorial-article-list" aria-label="教程目录">
          {articles.map((article) => (
            <button
              className={activeArticle.id === article.id ? "tutorial-article-item is-active" : "tutorial-article-item"}
              key={article.id}
              onClick={() => setActiveId(article.id)}
              type="button"
            >
              <span className="tutorial-article-icon">{article.icon}</span>
              <span className="tutorial-article-copy">
                <strong>{article.title}</strong>
                <span>{article.summary}</span>
              </span>
              <span className="tutorial-article-meta">{article.duration}</span>
            </button>
          ))}
        </aside>

        <article className="tutorial-reader">
          <header className="tutorial-reader-header">
            <span className="tutorial-reader-icon">{activeArticle.icon}</span>
            <div>
              <h4>{activeArticle.title}</h4>
              <p>{activeArticle.summary}</p>
            </div>
          </header>

          <div className="tutorial-section-list">
            {activeArticle.sections.map((section) => (
              <section className="tutorial-step" key={section.title}>
                <div className="tutorial-step-title">
                  <ChevronRightIcon />
                  <h5>{section.title}</h5>
                </div>
                <div className="tutorial-step-body">{section.body}</div>
              </section>
            ))}
          </div>
        </article>
      </div>
    </div>
  );
}
