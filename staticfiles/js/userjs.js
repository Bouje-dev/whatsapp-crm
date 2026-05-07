$(document).ready(function(){
    // Initialize Bootstrap tooltips
    $('[data-bs-toggle="tooltip"]').tooltip();
    
    // Initialize Bootstrap toast
    const successToastEl = document.getElementById('successToast');
    const successToast = successToastEl ? new bootstrap.Toast(successToastEl) : null;
    
    // Function to show toast messages
    function showToast(message) {
        if (successToast) {
            $('#toastMessage').text(message);
            successToast.show();
            setTimeout(() => successToast.hide(), 3000);
        }
    }

    // Check for success messages in URL on load
    const urlParams = new URLSearchParams(window.location.search);
    const newUrl = window.location.origin + window.location.pathname; // URL without query params

    if (urlParams.has('user_deleted')) {
        showToast('Team member removed successfully!');
        window.history.replaceState({}, document.title, newUrl);
    }
    
    if (urlParams.has('invitation_deleted')) {
        showToast('Invitation deleted successfully!');
        window.history.replaceState({}, document.title, newUrl);
    }
    
    if (urlParams.has('token_deleted')) {
        showToast('API Token deleted successfully!');
        window.history.replaceState({}, document.title, newUrl);
    }

    // Sidebar navigation logic: Show/Hide content sections
    $('.sidebar .nav-link').on('click', function(e) {
        e.preventDefault();
        // Remove active class from all sidebar links
        $('.sidebar .nav-link').removeClass('active');
        // Add active class to the clicked link
        $(this).addClass('active');

        // Get the target content section ID from data-section attribute
        const targetSectionId = $(this).data('section');
        
        // Hide all content panes
        $('.content-area-pane').removeClass('active');
        // Show the target content pane
        $('#' + targetSectionId).addClass('active');

        // For small screens, scroll to the top of the content section
        if ($(window).width() < 992) {
            $('html, body').animate({
                scrollTop: $('.main-content').offset().top - 20 // Scroll to main content start
            }, 300);
        }
    });

    // Toggle token visibility in input fields
    $('.toggle-token').click(function() {
        const input = $(this).closest('.input-group').find('input');
        const icon = $(this).find('i');
        
        if (input.attr('type') === 'password') {
            input.attr('type', 'text');
            icon.removeClass('fa-eye').addClass('fa-eye-slash');
        } else {
            input.attr('type', 'password');
            icon.removeClass('fa-eye-slash').addClass('fa-eye');
        }
    });
    
    // Show/hide API Token form logic
    // Buttons that can trigger the token form display
    $('#showTokenFormBtn_header, #showTokenFormBtn_empty_state').click(function() {
        $('#tokenFormSection').removeClass('d-none');
        // Hide both buttons that can trigger the form
        $('#showTokenFormBtn_header').addClass('d-none');
        $('#showTokenFormBtn_empty_state').addClass('d-none');
        // Also hide the empty state message if it's visible
        $('#no_tokens_message').addClass('d-none'); 

        // Scroll to the form
        $('html, body').animate({
            scrollTop: $('#tokenFormSection').offset().top - 30 
        }, 500);
    });
    
    $('#hideTokenFormBtn').click(function() {
        $('#tokenFormSection').addClass('d-none');
        // Show the "Add Token" button in the header again
        $('#showTokenFormBtn_header').removeClass('d-none'); 
        
        // If there are no tokens in the table, show the empty state message again
        if ($('#api-tokens .table tbody tr').length === 0) {
            $('#no_tokens_message').removeClass('d-none');
        }
    });
    
    // Show/hide Team Member form logic
    // Buttons that can trigger the team member form display
    $('#add_stuff_btn_header, #add_stuff_empty_state').click(function(e) { 
        e.preventDefault();
        $('#stuffFormSect').removeClass('d-none');
        // Hide both buttons that can trigger the form
        $('#add_stuff_btn_header').addClass('d-none');
        $('#add_stuff_empty_state').addClass('d-none');
        // Also hide the initial message for adding stuff
        $('#add_stuff_initial_message').addClass('d-none');
        // If there are no members and the empty state is visible, hide it
        $('#no_members_message').addClass('d-none');

        // Scroll to the form
        $('html, body').animate({
            scrollTop: $('#stuffFormSect').offset().top - 30 
        }, 500);
    });
    
    $('#hideStuffFormBtn').click(function(e) { 
        e.preventDefault();
        $('#stuffFormSect').addClass('d-none');
        // Show the "Add Member" button in the header again
        $('#add_stuff_btn_header').removeClass('d-none');

        // If there are no team members, show the empty state message
        if ($('#team-management .table tbody tr').length === 0) {
             $('#no_members_message').removeClass('d-none');
             $('#add_stuff_initial_message').addClass('d-none'); // Hide initial message if empty state is visible
        } else {
             $('#add_stuff_initial_message').removeClass('d-none'); // Show initial message if members exist
        }
    });
    
    // Submit team member form via AJAX
    $('.stuff_form').submit(function(e) {
        e.preventDefault();
        const form = $(this);
        const csrfToken = form.find('input[name="csrfmiddlewaretoken"]').val();
        
        $.ajax({
            type: 'POST',
            url: '{% url "invite_staff" %}',
            data: form.serialize(),
            headers: {
                'X-CSRFToken': csrfToken
            },
            beforeSend: function() {
                form.find('button[type="submit"]').prop('disabled', true)
                    .html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Sending...');
            },
            success: function(response) {
                if (response.success) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Invitation Sent!',
                        text: response.message,
                        timer: 2000,
                        showConfirmButton: false,
                        background: 'var(--background-secondary)',
                        color: 'var(--text-light)',
                        confirmButtonColor: 'var(--accent-color)'
                    }).then(() => {
                        location.reload();
                    });
                } else {
                    Swal.fire({
                        icon: 'error',
                        title: 'Error Sending Invitation',
                        text: response.message,
                        background: 'var(--background-secondary)',
                        color: 'var(--text-light)',
                        confirmButtonColor: 'var(--accent-color)'
                    });
                }
            },
            error: function(xhr) {
                Swal.fire({
                    icon: 'error',
                    title: 'Request Failed',
                    text: xhr.responseJSON?.message || 'An unexpected error occurred. Please try again.',
                    background: 'var(--background-secondary)',
                    color: 'var(--text-light)',
                    confirmButtonColor: 'var(--accent-color)'
                });
            },
            complete: function() {
                form.find('button[type="submit"]').prop('disabled', false)
                    .html('<i class="fas fa-paper-plane"></i> Send Invitation');
            }
        });
    });
    
    // Submit token form via AJAX
    $('.token-form').submit(function(e) {
        e.preventDefault();
        const form = $(this);
        const csrfToken = form.find('input[name="csrfmiddlewaretoken"]').val(); 
        
        $.ajax({
            type: 'POST',
            url: '{% url "access_token" %}',
            data: form.serialize(),
            headers: {
                'X-CSRFToken': csrfToken 
            },
            beforeSend: function() {
                form.find('button[type="submit"]').prop('disabled', true)
                    .html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...');
            },
            success: function(response) {
                if (response.success) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Token Saved!',
                        text: response.message,
                        timer: 2000,
                        showConfirmButton: false,
                        background: 'var(--background-secondary)',
                        color: 'var(--text-light)',
                        confirmButtonColor: 'var(--accent-color)'
                    }).then(() => {
                        location.reload();
                    });
                } else {
                    Swal.fire({
                        icon: 'error',
                        title: 'Error Saving Token',
                        text: response.message,
                        background: 'var(--background-secondary)',
                        color: 'var(--text-light)',
                        confirmButtonColor: 'var(--accent-color)'
                    });
                }
            },
            error: function(xhr) {
                Swal.fire({
                    icon: 'error',
                    title: 'Request Failed',
                    text: xhr.responseJSON?.message || 'An unexpected error occurred. Please try again.',
                    background: 'var(--background-secondary)',
                    color: 'var(--text-light)',
                    confirmButtonColor: 'var(--accent-color)'
                });
            },
            complete: function() {
                form.find('button[type="submit"]').prop('disabled', false)
                    .html('<i class="fas fa-save"></i> Save Token');
            }
        });
    });

    // Handle initial state of forms and empty messages in Team Management and API Tokens
    // Team Management
    if ($('#team-management .table tbody tr').length === 0) {
        // No team members, show the empty state invite button by default
        $('#add_stuff_empty_state').removeClass('d-none');
        $('#add_stuff_btn_header').addClass('d-none');
        $('#no_members_message').removeClass('d-none'); // Ensure empty state is visible
    } else {
        // Team members exist, show the header invite button
        $('#add_stuff_btn_header').removeClass('d-none');
        $('#add_stuff_empty_state').addClass('d-none');
        $('#add_stuff_initial_message').removeClass('d-none'); // Show initial message if members exist
        $('#no_members_message').addClass('d-none'); // Hide empty state if members exist
    }

    // API Tokens
    if ($('#api-tokens .table tbody tr').length === 0) {
        // No tokens, show the empty state add token button by default
        $('#showTokenFormBtn_empty_state').removeClass('d-none');
        $('#showTokenFormBtn_header').addClass('d-none');
        $('#no_tokens_message').removeClass('d-none'); // Ensure empty state is visible
    } else {
        // Tokens exist, show the header add token button
        $('#showTokenFormBtn_header').removeClass('d-none');
        $('#showTokenFormBtn_empty_state').addClass('d-none');
        $('#no_tokens_message').addClass('d-none'); // Hide empty state if tokens exist
    }



                                            const multiselect = document.getElementById('productlist-multiselect');
                                            const dropdown = document.getElementById('productlist-dropdown');
                                            const selectedDiv = document.getElementById('productlist-selected');
                                            const hiddenInput = document.getElementById('productlist-hidden');
                                            let selected = [];

                                            // Toggle dropdown
                                            multiselect.addEventListener('click', function(e) {
                                                if (e.target.tagName !== 'INPUT') {
                                                    dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
                                                }
                                            });

                                            // Hide dropdown on outside click
                                            document.addEventListener('click', function(e) {
                                                if (!multiselect.contains(e.target)) {
                                                    dropdown.style.display = 'none';
                                                }
                                            });

                                            // Handle checkbox selection
                                            dropdown.addEventListener('change', function(e) {
                                                const checkboxes = dropdown.querySelectorAll('input[type="checkbox"]');
                                                if (e.target.value === 'all') {
                                                    // If "All Products" is checked, uncheck others
                                                    if (e.target.checked) {
                                                        checkboxes.forEach(cb => {
                                                            if (cb.value !== 'all') cb.checked = false;
                                                        });
                                                        selected = ['all'];
                                                    } else {
                                                        selected = [];
                                                    }
                                                } else {
                                                    // If any other is checked, uncheck "All Products"
                                                    dropdown.querySelector('input[value="all"]').checked = false;
                                                    selected = Array.from(checkboxes)
                                                        .filter(cb => cb.checked && cb.value !== 'all')
                                                        .map(cb => cb.value);
                                                }
                                                updateSelectedDisplay();
                                            });

                                            function updateSelectedDisplay() {
                                                selectedDiv.innerHTML = '';
                                                if (selected.length === 0) {
                                                    selectedDiv.innerHTML = '<span class="text-muted">Select products...</span>';
                                                    hiddenInput.value = '';
                                                } else if (selected.includes('all')) {
                                                    selectedDiv.innerHTML = '<span class="badge badge-primary">All Products</span>';
                                                    hiddenInput.value = 'all';
                                                } else {
                                                    selected.forEach(val => {
                                                        // Find label text
                                                        const label = dropdown.querySelector('input[value="' + val + '"]').parentNode.textContent.trim();
                                                        const badge = document.createElement('span');
                                                        badge.className = 'badge badge-secondary';
                                                        badge.textContent = label;
                                                        selectedDiv.appendChild(badge);
                                                    });
                                                    hiddenInput.value = selected.join(',');
                                                }
                                            }
                                            // Initialize
                                            updateSelectedDisplay();
     


});
 