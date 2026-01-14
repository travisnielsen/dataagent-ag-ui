import type { Metadata } from "next";

import { Providers } from "@/components/Providers";
import "./globals.css";
import "@copilotkit/react-ui/styles.css";

export const metadata: Metadata = {
  title: "Logistics Assistant",
  description: "Sample application showcasing CopilotKit for logistics data analysis",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={"antialiased"}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
