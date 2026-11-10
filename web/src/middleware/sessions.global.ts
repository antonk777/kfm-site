import { SESSIONS_PUBLIC } from "~/lib/flags";

export default defineNuxtRouteMiddleware((to) => {
  if (!SESSIONS_PUBLIC && to.path.startsWith("/sessions")) return navigateTo("/");
});
