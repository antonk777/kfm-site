import { createRouter, createWebHistory } from "vue-router";
import PlayerPage from "./views/PlayerPage.vue";
import LandingPage from "./views/LandingPage.vue";
import LeaderboardPage from "./views/LeaderboardPage.vue";
import SessionsPage from "./views/SessionsPage.vue";
import SessionDetailPage from "./views/SessionDetailPage.vue";
import { SESSIONS_PUBLIC } from "./lib/flags";

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior() {
    return { top: 0 };
  },
  routes: [
    { path: "/", name: "home", component: LandingPage },
    { path: "/sessions", name: "sessions", component: SessionsPage },
    { path: "/sessions/:id", name: "session", component: SessionDetailPage, props: true },
    { path: "/players", name: "players", component: LeaderboardPage },
    { path: "/players/:id", name: "player", component: PlayerPage, props: true },
    // Bare numeric path (/76561198006804047/) → canonical player URL.
    { path: "/:id(\\d+)", redirect: (to) => ({ path: `/players/${to.params.id}` }) },
    // Unknown paths → home.
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach((to) => {
  if (!SESSIONS_PUBLIC && (to.name === "sessions" || to.name === "session")) return { path: "/" };
});
