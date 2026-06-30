import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import { exampleWidgetConfig } from "../config/exampleWidgetConfig";
import { ChatwootWidgetAdapter } from "../integrations/ChatwootWidgetAdapter";
import type { GenericWidgetConfig } from "../types";

const chatwootConfig: GenericWidgetConfig = {
  ...exampleWidgetConfig,
  provider: { name: "Chatwoot", type: "script" }
};

export function ChatwootWidgetExample({ baseUrl, websiteToken }: { baseUrl: string; websiteToken: string }) {
  return (
    <GenericWidgetWrapper config={chatwootConfig}>
      {(state) => (
        <ChatwootWidgetAdapter
          baseUrl={baseUrl}
          websiteToken={websiteToken}
          state={state}
          settings={{
            position: "right",
            type: "standard",
            launcherTitle: chatwootConfig.labels.launcherAriaLabel
          }}
          customAttributes={{
            provider: chatwootConfig.provider.name,
            providerType: chatwootConfig.provider.type
          }}
        />
      )}
    </GenericWidgetWrapper>
  );
}
