import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router";
import "flag-icons/css/flag-icons.min.css";
import "./styles/fonts.css";
import "./styles/base.css";

createApp(App).use(router).mount("#app");
