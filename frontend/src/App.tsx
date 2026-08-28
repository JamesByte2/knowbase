import { App as AntApp, Button, Layout, Menu, theme } from "antd";
import { BookOutlined, CommentOutlined, LogoutOutlined } from "@ant-design/icons";
import { useState } from "react";
import { client } from "./api/client";
import KnowledgeBasesPage from "./pages/KnowledgeBases";
import LoginPage from "./pages/Login";

const { Header, Sider, Content } = Layout;

function Shell({ onLogout }: { onLogout: () => void }) {
  const { token } = theme.useToken();
  const [page, setPage] = useState("kbs");

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" style={{ borderRight: `1px solid ${token.colorBorderSecondary}` }}>
        <div style={{ padding: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 16 }}>KnowBase</div>
          <div style={{ color: token.colorTextTertiary, fontSize: 12 }}>AI 知识库问答</div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[page]}
          onClick={(e) => setPage(e.key)}
          items={[
            { key: "kbs", icon: <BookOutlined />, label: "知识库" },
            { key: "chat", icon: <CommentOutlined />, label: "对话", disabled: true },
          ]}
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
          {page === "kbs" ? <KnowledgeBasesPage /> : null}
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
