import AskVera from "./AskVera";

declare global {
    interface Window {
        AskVera: typeof AskVera;
    }
}

window.AskVera = AskVera;

export default AskVera;
export type {
    AskVeraInitConfig,
    AskVeraSdk,
} from "./AskVera";
