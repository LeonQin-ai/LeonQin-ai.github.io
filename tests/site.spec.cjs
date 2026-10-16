const {test,expect}=require('@playwright/test');

test('homepage, series links, filtering, search and theme',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page).toHaveTitle(/Leon Qin/);
  await expect(page.locator('[data-post]')).toHaveCount(8);
  await page.getByRole('button',{name:'多 Agent 协作',exact:true}).click();
  await expect(page.locator('[data-post]:visible')).toHaveCount(2);
  await page.getByRole('button',{name:/全部文章/}).click();
  await page.keyboard.press('/');
  await expect(page.getByRole('searchbox')).toBeFocused();
  await page.getByRole('searchbox').fill('百万');
  await expect(page.locator('[data-post]:visible')).toHaveCount(1);
  await page.getByRole('searchbox').fill('not-an-article-xyz');
  await expect(page.locator('.empty-state')).toBeVisible();
  await page.getByRole('button',{name:'清除筛选'}).click();
  await expect(page.locator('[data-post]:visible')).toHaveCount(8);
  await page.getByRole('button',{name:'切换深浅主题'}).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.getByRole('button',{name:'切换深浅主题'}).click();
  await page.screenshot({path:'test-results/home-desktop.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('all eight articles have content, valid navigation and rendered diagrams',async({page})=>{
  await page.goto('/');
  const links=await page.locator('.card-title').evaluateAll(items=>items.map(item=>item.getAttribute('href')));
  for(const link of links){
    const response=await page.goto(link);expect(response.status()).toBe(200);
    await expect(page.locator('article.prose')).toBeVisible();
    await expect(page.locator('.desktop-toc nav a')).not.toHaveCount(0);
    await expect(page.locator('.post-navigation a')).toHaveCount(2);
    expect(await page.locator('h1').textContent()).toBeTruthy();
  }
  await page.goto('/articles/agent-runtime-in-c/');
  await expect(page.locator('.article-diagram img')).toBeVisible();
  await expect(page.locator('.article-diagram img')).toHaveJSProperty('naturalWidth',700);
  const anchor=page.locator('.desktop-toc nav a').nth(1);
  await anchor.click();expect(page.url()).toContain('#h-');
  await page.context().grantPermissions(['clipboard-read','clipboard-write']);
  await page.getByRole('button',{name:'复制代码',exact:true}).first().click();
  await expect(page.getByRole('button',{name:'复制代码',exact:true}).first()).toHaveText('已复制');
  expect(await page.evaluate(()=>navigator.clipboard.readText())).toContain('localhost:18300');
  await page.screenshot({path:'test-results/article-desktop.png',fullPage:true});
});

test('mobile: no page overflow and working reading/navigation controls',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.locator('h1')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'test-results/home-mobile.png',fullPage:true});
  await page.getByRole('link',{name:/从第一篇读起/}).click();
  await expect(page.locator('.mobile-toc')).toBeVisible();
  await page.locator('.mobile-toc summary').click();
  await page.locator('.mobile-toc nav a').nth(1).click();
  expect(page.url()).toContain('#h-');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.goto('/articles/million-task-benchmark/');
  await expect(page.locator('.table-scroll')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'test-results/article-mobile.png',fullPage:true});
});
