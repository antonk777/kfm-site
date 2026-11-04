import { createRouter, createWebHistory } from "vue-router";
import PlayerPage from "./views/PlayerPage.vue";
import LandingPage from "./views/LandingPage.vue";
import LeaderboardPage from "./views/LeaderboardPage.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: LandingPage },
    { path: "/players", name: "players", component: LeaderboardPage },
    { path: "/players/:id", name: "player", component: PlayerPage, props: true },
    // Bare numeric path (/76561198006804047/) → canonical player URL.
    { path: "/:id(\\d+)", redirect: (to) => ({ path: `/players/${to.params.id}` }) },
    // Unknown paths → home.
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
