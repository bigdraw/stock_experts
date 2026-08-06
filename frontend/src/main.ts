import { createApp } from 'vue'
import { createPinia } from 'pinia'
import naive from 'naive-ui'
import router from './router'
import App from './App.vue'
import '@fontsource/nunito/400.css'
import '@fontsource/nunito/600.css'
import '@fontsource/nunito/700.css'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(naive)

// ISSUE-030: catch render errors so a single broken view (e.g. a render fn
// throwing) doesn't blank the whole app shell — log instead of white-screen.
app.config.errorHandler = (err, _instance, info) => {
  // eslint-disable-next-line no-console
  console.error('[Vue render error]', info, err)
}

app.mount('#app')
