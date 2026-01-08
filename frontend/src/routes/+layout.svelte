<script>
  import '../app.css';
</script>

<div class="min-h-screen bg-gray-50">
  <nav class="bg-white shadow-sm border-b">
    <div class="max-w-7xl mx-auto px-4 py-3">
      <div class="flex items-center justify-between">
        <a href="/" class="text-xl font-bold text-green-700">
          🌿 DSH Dataset Search
        </a>
        <div class="flex gap-4">
          <a href="/" class="text-gray-600 hover:text-green-700">Search</a>
          <a href="/datasets" class="text-gray-600 hover:text-green-700">Browse</a>
        </div>
      </div>
    </div>
  </nav>
  
  <main class="max-w-7xl mx-auto px-4 py-8">
    <slot />
  </main>
  
  <footer class="border-t mt-auto py-4 text-center text-gray-500 text-sm">
    DSH ETL Search AI - Environmental Dataset Discovery
  </footer>
</div>