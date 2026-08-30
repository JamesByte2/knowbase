import { App as AntApp, Button, Layout, Menu, Tabs, theme } from "antd";
import { BookOutlined, LogoutOutlined } from "@ant-design/icons";
import { useState } from "react";
import { client, KnowledgeBase } from "./api/client";
import ChatPage from "./pages/Chat";
import DocumentsPage from "./pages/Documents";
import KnowledgeBasesPage from "./pages/KnowledgeBases";
import LoginPage from "./pages/Login";

const { Header, Sider, Content } = Layout;

function KBWorkbench({ kb, onBack }: { kb: KnowledgeBase; onBack: () => void }) {
  const [docsChanged, setDocsChanged] = useState(0);
  return (
    <div style={{ maxWidth: 860, margin: "0 auto" }}>
      <Button type="link" style={{ padding: 0, marginBottom: 8 }} onClick={onBack}>
        ← 返回知识库列表
      </Button>
      <Tabs
        defaultActiveKey="chat"
        items={[
          { key: "chat", label: "对话提问", children: <ChatPage kb={kb} key={`chat-${docsChanged}`} /> },
          {
            key: "docs",
            label: "文档管理",
            children: <DocumentsPage kb={kb} onChanged={() => setDocsChanged((n) => n + 1)} />,
          },
        ]}
      />
    </div>
  );
}

function Shell({ onLogout }: { onLogout: () => void }) {
  const { token } = theme.useToken();
  const [page, setPage] = useState("kbs");
  const [activeKb, setActiveKb] = useState<KnowledgeBase | null>(null);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" style={{ borderRight: `1px solid ${token.colorBorderSecondary}` }}>
        <div style={{ padding: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 16 }}>KnowBase</div>
          <div style={{ color: token.colorTextTertiary, fontSize: 12 }}>AI 知识库问答</div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={["kbs"]}
          onClick={(e) => {
            setPage(e.key);
            setActiveKb(null);
          }}
          items={[{ key: "kbs", icon: <BookOutlined />, label: "知识库" }]}
        />
        <Button
          type="text"
          icon={<LogoutOutlined />}
          onClick={onLogout}
          style={{ position: "absolute", bottom: 16, width: "100%" }}
        >
          退出登录
        </Button>
      </Sider>
      <Layout>
        <Header style={{ background: token.colorBgContainer, borderBottom: `1px solid ${token.colorBorderSecondary}` }} />
        <Content style={{ padding: 24, background: token.colorBgLayout, overflow: "auto" }}>
          {activeKb ? (
            <KBWorkbench kb={activeKb} onBack={() => setActiveKb(null)} />
          ) : (
            <KnowledgeBasesPage onOpen={setActiveKb} />
          )}
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  const { message } = AntApp.useApp();
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));

  if (!token) {
    return (
      <AntApp>
        <LoginPage
          onLogin={() => {
            message.success("登录成功");
            setToken(localStorage.getItem("token"));
          }}
        />
      </AntApp>
    );
  }

  return (
    <AntApp>
      <Shell
        onLogout={() => {
          localStorage.removeItem("token");
          client.defaults.headers.common["Authorization"] = undefined;
          setToken(null);
        }}
      />
    </AntApp>
  );
}
