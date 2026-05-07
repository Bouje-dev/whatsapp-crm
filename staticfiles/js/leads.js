
  const refresh_leads = document.getElementById('refresh-leads-icon');
refresh_leads.addEventListener('click', function() {
    const productsku = document.getElementById('product-leads-filter').value;
    

fetch("{% url 'leadstracking' %}", {
    method: 'POST',
    headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': '{{ csrf_token }}'
    },
    body: new URLSearchParams({
         'sku': productsku
     })
})
.then(response => response.json())
.then(response => {
    if (response.status === 'success') {
        // Update the UI with the new leads data
        document.getElementById('leadsTable').innerHTML = response.data;
    } else {
        // Handle error case
        console.error('Error fetching leads:', response.message);
    }
}); 
}); 
                        
 
 