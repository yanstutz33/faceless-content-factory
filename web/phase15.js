let commerceState={summary:{},products:[],campaigns:[],destinations:[]};

const money=value=>Number(value||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const commerceStatus={validated:'VALIDADO',blocked:'BLOQUEADO',draft:'RASCUNHO',ready_for_package:'PRONTO PARA PACOTE',packaged:'PACOTE PRONTO'};

function renderCommerce(){
  const summary=commerceState.summary;
  document.querySelector('#commerce-badge').textContent=summary.campaigns||0;
  document.querySelector('#commerce-summary').innerHTML=[
    ['Produtos',summary.products||0,'catálogo local'],
    ['Campanhas',summary.campaigns||0,'operação separada'],
    ['Conversões',summary.conversions||0,`${summary.clicks||0} cliques`],
    ['Resultado',money(summary.profit),`${money(summary.commission)} em comissão`],
  ].map(([label,value,detail])=>`<article><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(detail)}</small></article>`).join('');

  const products=document.querySelector('#commerce-products');
  products.innerHTML=commerceState.products.length?commerceState.products.map(product=>`<article class="commerce-product ${product.status}"><div><span class="tag">${esc(commerceStatus[product.status]||product.status)}</span><h4>${esc(product.title)}</h4><p>ID ${esc(product.external_id)} · ${money(product.price)}</p></div><div class="commerce-product-meta"><b>${product.validation.passed?'✓ Direitos e vínculo conferidos':'! '+product.validation.errors.length+' pendência(s)'}</b><small>${esc(product.validation.errors.slice(0,2).join(' · ')||'Pronto para campanhas')}</small></div></article>`).join(''):'<div class="commerce-empty">Cadastre o primeiro produto para iniciar a linha comercial.</div>';

  const campaigns=document.querySelector('#commerce-campaigns');
  campaigns.innerHTML=commerceState.campaigns.length?commerceState.campaigns.map(campaign=>`<article class="commerce-campaign"><div class="commerce-campaign-head"><div><span class="tag">${esc(commerceStatus[campaign.status]||campaign.status)}</span><h4>${esc(campaign.name)}</h4><p>${esc(campaign.product_title)} · ${esc(campaign.destination_label)}</p></div><b>${money(campaign.commission)}</b></div><div class="commerce-kpis"><span><b>${Number(campaign.clicks).toLocaleString('pt-BR')}</b> cliques</span><span><b>${Number(campaign.conversions).toLocaleString('pt-BR')}</b> conversões</span><span><b>${campaign.roi===null?'—':campaign.roi+'%'}</b> ROI</span></div><div class="commerce-campaign-actions"><button class="secondary" data-commerce-metrics="${esc(campaign.id)}">Registrar resultado</button>${campaign.job_id?`<button class="primary" data-commerce-package="${esc(campaign.id)}" ${campaign.status==='packaged'?'disabled':''}>${campaign.status==='packaged'?'Pacote preparado':'Preparar pacote'}</button>`:'<button class="secondary" disabled>Vincule uma produção</button>'}</div></article>`).join(''):'<div class="commerce-empty">Crie uma campanha depois de validar um produto.</div>';

  const valid=commerceState.products.filter(product=>product.status==='validated');
  document.querySelector('#campaign-product').innerHTML=valid.length?valid.map(product=>`<option value="${esc(product.id)}">${esc(product.title)}</option>`).join(''):'<option value="">Cadastre um produto validado primeiro</option>';
}

async function loadCommerce(){
  const root=document.querySelector('#commerce-summary');root.setAttribute('aria-busy','true');
  try{
    const [overview,jobs]=await Promise.all([api('/api/commerce-center'),api('/api/jobs?limit=200')]);
    commerceState=overview;renderCommerce();
    const approved=jobs.filter(job=>job.status==='approved');
    document.querySelector('#campaign-job').innerHTML='<option value="">Vincular depois</option>'+approved.map(job=>`<option value="${esc(job.id)}">${esc(job.topic)}</option>`).join('');
  }catch(error){document.querySelector('#commerce-products').innerHTML='<div class="commerce-empty">Não foi possível abrir a central comercial.</div>';toast(error.message,'error')}
  finally{root.removeAttribute('aria-busy')}
}

const productDialog=document.querySelector('#commerce-product-dialog');
const campaignDialog=document.querySelector('#commerce-campaign-dialog');
const metricsDialog=document.querySelector('#commerce-metrics-dialog');
document.querySelector('#new-commerce-product').onclick=()=>productDialog.showModal();
document.querySelector('#new-commerce-campaign').onclick=()=>{if(!commerceState.products.some(product=>product.status==='validated'))return toast('Valide um produto antes de criar a campanha.','error');campaignDialog.showModal()};
document.querySelector('#refresh-commerce').onclick=loadCommerce;
document.querySelectorAll('[data-commerce-close]').forEach(button=>button.onclick=()=>productDialog.close());
document.querySelectorAll('[data-campaign-close]').forEach(button=>button.onclick=()=>campaignDialog.close());
document.querySelectorAll('[data-metrics-close]').forEach(button=>button.onclick=()=>metricsDialog.close());

document.querySelector('#commerce-product-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const submit=form.querySelector('[type=submit]');const data=new FormData(form);const error=form.querySelector('[data-commerce-product-error]');error.textContent='';submit.disabled=true;
  const claimText=String(data.get('claim_text')||'').trim();const claimSource=String(data.get('claim_source')||'').trim();
  const payload={product_id:data.get('product_id'),title:data.get('title'),product_url:data.get('product_url'),affiliate_url:data.get('affiliate_url'),price:Number(data.get('price')||0),exact_product_confirmed:!!data.get('exact_product_confirmed'),affiliate_disclosure:!!data.get('affiliate_disclosure'),assets:[{name:data.get('asset_name'),license_type:data.get('license_type'),source_url:data.get('source_url'),approved:!!data.get('asset_approved')}],claims:claimText||claimSource?[{text:claimText,source:claimSource}]:[]};
  try{const product=await api('/api/commerce-center/products',{method:'POST',body:JSON.stringify(payload)});productDialog.close();form.reset();toast(product.status==='validated'?'Produto validado e salvo.':'Produto salvo com pendências.','success');await loadCommerce()}
  catch(reason){error.textContent=reason.message}finally{submit.disabled=false}
});

document.querySelector('#commerce-campaign-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const submit=form.querySelector('[type=submit]');const data=new FormData(form);const error=form.querySelector('[data-commerce-campaign-error]');error.textContent='';submit.disabled=true;
  try{await api('/api/commerce-center/campaigns',{method:'POST',body:JSON.stringify({name:data.get('name'),product_id:data.get('product_id'),job_id:data.get('job_id'),destination:data.get('destination'),cost:Number(data.get('cost')||0),notes:data.get('notes')})});campaignDialog.close();form.reset();toast('Campanha criada sem publicar nada.','success');await loadCommerce()}
  catch(reason){error.textContent=reason.message}finally{submit.disabled=false}
});

document.querySelector('#commerce-campaigns').addEventListener('click',async event=>{
  const metrics=event.target.closest('[data-commerce-metrics]');
  if(metrics){const campaign=commerceState.campaigns.find(item=>item.id===metrics.dataset.commerceMetrics);const form=document.querySelector('#commerce-metrics-form');form.campaign_id.value=campaign.id;form.clicks.value=campaign.clicks;form.conversions.value=campaign.conversions;form.commission.value=campaign.commission;form.cost.value=campaign.cost;metricsDialog.showModal();return}
  const packageButton=event.target.closest('[data-commerce-package]');
  if(packageButton){packageButton.disabled=true;try{await api(`/api/commerce-center/campaigns/${encodeURIComponent(packageButton.dataset.commercePackage)}/package`,{method:'POST',body:JSON.stringify({duration:30}),timeoutMs:120000});toast('Pacote comercial preparado; nenhum upload foi feito.','success');await loadCommerce()}catch(error){toast(error.message,'error')}finally{packageButton.disabled=false}}
});

document.querySelector('#commerce-metrics-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const submit=form.querySelector('[type=submit]');const data=new FormData(form);const error=form.querySelector('[data-commerce-metrics-error]');error.textContent='';submit.disabled=true;
  try{await api(`/api/commerce-center/campaigns/${encodeURIComponent(data.get('campaign_id'))}/metrics`,{method:'POST',body:JSON.stringify({clicks:Number(data.get('clicks')||0),conversions:Number(data.get('conversions')||0),commission:Number(data.get('commission')||0),cost:Number(data.get('cost')||0)})});metricsDialog.close();toast('Resultado comercial registrado.','success');await loadCommerce()}
  catch(reason){error.textContent=reason.message}finally{submit.disabled=false}
});

loadCommerce();
