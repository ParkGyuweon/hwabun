package com.cosmetic.collector.event.api;

import com.cosmetic.collector.common.GlobalExceptionHandler;
import com.cosmetic.collector.event.application.EventPublishException;
import com.cosmetic.collector.event.application.EventPublishOverloadedException;
import com.cosmetic.collector.event.application.EventPublisher;
import com.cosmetic.collector.event.application.PublishSummary;
import com.cosmetic.collector.event.api.validation.EventBatchSemanticValidator;
import com.cosmetic.collector.event.observability.CollectorMetrics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import java.util.concurrent.CompletableFuture;

import static org.assertj.core.api.Assertions.assertThat;

import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class EventControllerTest {

    private EventPublisher publisher;
    private CollectorMetrics metrics;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        publisher = mock(EventPublisher.class);
        metrics = mock(CollectorMetrics.class);

        LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();

        mockMvc = standaloneSetup(new EventController(
                        publisher, metrics, new EventBatchSemanticValidator(validator)))
                .setControllerAdvice(new GlobalExceptionHandler(metrics))
                .setValidator(validator)
                .build();
    }

    @Test
    void acceptsAValidBatchAfterPublishing() throws Exception {
        when(publisher.publish(anyString(), anyList()))
                .thenReturn(CompletableFuture.completedFuture(new PublishSummary(1)));

        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "0.2.0-draft",
                                  "events": [{
                                    "schema_version": "0.2.0-draft",
                                    "event_id": "evt-001",
                                    "event_name": "product_click",
                                    "intent": "comparison",
                                    "occurred_at": "2026-08-27T14:30:00Z",
                                    "persona_id": null,
                                    "session_id": "session-001",
                                    "page_view_id": "page-view-001",
                                    "sequence_no": 1,
                                    "page_type": "product_list",
                                    "product_id": "product-001",
                                    "actor_type": "user",
                                    "environment": "local",
                                    "properties": {"position": 1}
                                  }]
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isAccepted())
                .andExpect(header().exists("X-Request-Id"))
                .andExpect(jsonPath("$.accepted").value(1))
                .andExpect(jsonPath("$.rejected").value(0));

        verify(metrics).recordReceived(1);
        verify(publisher).publish(anyString(), anyList());
    }

    @Test
    void acceptsNavigationClickWithSessionIntent() throws Exception {
        when(publisher.publish(anyString(), anyList()))
                .thenReturn(CompletableFuture.completedFuture(new PublishSummary(1)));

        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "0.2.0-draft",
                                  "events": [{
                                    "schema_version": "0.2.0-draft",
                                    "event_id": "evt-navigation-001",
                                    "event_name": "navigation_click",
                                    "intent": "session",
                                    "occurred_at": "2026-08-27T14:30:00Z",
                                    "session_id": "session-001",
                                    "page_view_id": "page-view-001",
                                    "sequence_no": 1,
                                    "page_type": "product_list",
                                    "actor_type": "user",
                                    "environment": "local",
                                    "properties": {
                                      "target": "/cart",
                                      "entry_source": "breadcrumb"
                                    }
                                  }]
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.accepted").value(1))
                .andExpect(jsonPath("$.rejected").value(0));

        verify(metrics).recordReceived(1);
        verify(publisher).publish(anyString(), anyList());
    }

    @Test
    void rejectsInvalidPurchaseReasonsWithoutRepublishingTheInvalidEvent() throws Exception {
        when(publisher.publish(anyString(), anyList()))
                .thenReturn(CompletableFuture.completedFuture(new PublishSummary(1)));

        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "0.2.0-draft",
                                  "events": [
                                    {
                                      "schema_version": "0.2.0-draft", "event_id": "evt-valid",
                                      "event_name": "purchase_reason_select", "intent": "validation",
                                      "occurred_at": "2026-08-27T14:30:00Z", "session_id": "session-001",
                                      "page_view_id": "page-view-001", "sequence_no": 1, "page_type": "cart",
                                      "actor_type": "user", "environment": "local",
                                      "properties": {"order_id": "order-001", "reasons": ["ingredient"]}
                                    },
                                    {
                                      "schema_version": "0.2.0-draft", "event_id": "evt-invalid",
                                      "event_name": "purchase_reason_select", "intent": "validation",
                                      "occurred_at": "2026-08-27T14:30:00Z", "session_id": "session-001",
                                      "page_view_id": "page-view-001", "sequence_no": 2, "page_type": "cart",
                                      "actor_type": "user", "environment": "local",
                                      "properties": {"order_id": "order-001", "reasons": ["invalid_reason"]}
                                    }
                                  ]
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.accepted").value(1))
                .andExpect(jsonPath("$.rejected").value(1))
                .andExpect(jsonPath("$.rejections[0].event_index").value(1))
                .andExpect(jsonPath("$.rejections[0].event_id").value("evt-invalid"))
                .andExpect(jsonPath("$.rejections[0].code").value("invalid_property_enum"));

        verify(publisher).publish(anyString(), anyList());
        verify(metrics).recordEventRejected(1);
        verify(metrics).recordValidationRejected("invalid_property_enum");
    }

    @Test
    void rejectsAnEmptyBatch() throws Exception {
        mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "draft",
                                  "events": []
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_EVENT_BATCH"));

        verify(metrics).recordValidationRejected("invalid_event_batch");
    }

    @Test
    void rejectsAnEventWithoutEventNameButStillPublishesValidEvents() throws Exception {
        when(publisher.publish(anyString(), anyList()))
                .thenReturn(CompletableFuture.completedFuture(new PublishSummary(1)));

        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "0.2.0-draft",
                                  "events": [
                                    {
                                      "schema_version": "0.2.0-draft", "event_id": "evt-valid",
                                      "event_name": "product_click", "intent": "comparison",
                                      "occurred_at": "2026-08-27T14:30:00Z", "session_id": "session-001",
                                      "page_view_id": "page-view-001", "sequence_no": 1,
                                      "page_type": "product_list", "actor_type": "user",
                                      "environment": "local", "properties": {}
                                    },
                                    {
                                      "schema_version": "0.2.0-draft", "event_id": "evt-missing-name",
                                      "intent": "comparison", "occurred_at": "2026-08-27T14:30:00Z",
                                      "session_id": "session-001", "page_view_id": "page-view-001",
                                      "sequence_no": 2, "page_type": "product_list", "actor_type": "user",
                                      "environment": "local", "properties": {}
                                    }
                                  ]
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.accepted").value(1))
                .andExpect(jsonPath("$.rejected").value(1))
                .andExpect(jsonPath("$.rejections[0].event_index").value(1))
                .andExpect(jsonPath("$.rejections[0].event_id").value("evt-missing-name"))
                .andExpect(jsonPath("$.rejections[0].code").value("missing_required_property"));

        verify(publisher).publish(anyString(), anyList());
    }

    @Test
    void rejectsNullEventsWithoutDereferencingTheirEventId() throws Exception {
        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "0.2.0-draft",
                                  "events": [null]
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.accepted").value(0))
                .andExpect(jsonPath("$.rejected").value(1))
                .andExpect(jsonPath("$.rejections[0].event_index").value(0))
                .andExpect(jsonPath("$.rejections[0].event_id").value(nullValue()))
                .andExpect(jsonPath("$.rejections[0].code").value("null_event"));

        verifyNoInteractions(publisher);
    }

    @Test
    void choosesTheDocumentedPrimaryCodeWhenAnEventHasMultipleViolations() throws Exception {
        when(publisher.publish(anyString(), anyList()))
                .thenReturn(CompletableFuture.completedFuture(new PublishSummary(0)));

        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "0.2.0-draft",
                                  "events": [{
                                    "schema_version": "0.2.0-draft", "event_id": "evt-invalid",
                                    "event_name": "purchase", "intent": "comparison",
                                    "occurred_at": "2026-08-27T14:30:00Z", "session_id": "session-001",
                                    "page_view_id": "page-view-001", "sequence_no": 1,
                                    "page_type": "cart", "actor_type": "user", "environment": "local",
                                    "properties": {}
                                  }]
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.rejected").value(1))
                .andExpect(jsonPath("$.rejections[0].code").value("event_intent_mismatch"));

        verifyNoInteractions(publisher);
    }

    @Test
    void prioritizesMissingTenantOverAnInvalidPropertiesType() throws Exception {
        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "0.3.0-draft",
                                  "events": [{
                                    "schema_version": "0.3.0-draft", "event_id": "evt-invalid",
                                    "event_name": "product_click", "intent": "comparison",
                                    "occurred_at": "2026-08-27T14:30:00Z", "session_id": "session-001",
                                    "page_view_id": "page-view-001", "sequence_no": 1,
                                    "page_type": "product_list", "actor_type": "user", "environment": "local",
                                    "properties": []
                                  }]
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.accepted").value(0))
                .andExpect(jsonPath("$.rejected").value(1))
                .andExpect(jsonPath("$.rejections[0].code").value("missing_required_property"));

        verifyNoInteractions(publisher);
    }

    @Test
    void returnsPayloadTooLargeWhenTheBatchExceedsTheEventLimit() throws Exception {
        String events = String.join(",", java.util.Collections.nCopies(101, """
                {
                  "schema_version": "0.2.0-draft",
                  "event_id": "evt-001",
                  "event_name": "product_click",
                  "intent": "comparison",
                  "occurred_at": "2026-08-27T14:30:00Z",
                  "session_id": "session-001",
                  "page_view_id": "page-view-001",
                  "sequence_no": 1,
                  "page_type": "product_list",
                  "actor_type": "user",
                  "environment": "local"
                }
                """));

        mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"schema_version\":\"0.2.0-draft\",\"events\":[" + events + "]}"))
                .andExpect(status().isPayloadTooLarge())
                .andExpect(jsonPath("$.code").value("EVENT_BATCH_TOO_LARGE"));

        verifyNoInteractions(publisher);
        verify(metrics).recordValidationRejected("event_batch_too_large");
    }

    @Test
    void discardsAnEventWithoutRequiredIdentifiers() throws Exception {
        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "0.2.0-draft",
                                  "events": [{
                                    "schema_version": "0.2.0-draft",
                                    "event_name": "product_click",
                                    "intent": "comparison",
                                    "occurred_at": "2026-08-27T14:30:00Z",
                                    "persona_id": null
                                  }]
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.accepted").value(0))
                .andExpect(jsonPath("$.rejected").value(1))
                .andExpect(jsonPath("$.rejections[0].event_index").value(0));

        verify(metrics).recordEventRejected(1);
    }

    @Test
    void returnsServiceUnavailableWhenKafkaPublishingFails() throws Exception {
        when(publisher.publish(anyString(), anyList())).thenReturn(CompletableFuture.failedFuture(
                new EventPublishException("publish failed", new RuntimeException("Kafka unavailable"))
        ));

        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "schema_version": "0.2.0-draft",
                                  "events": [{
                                    "schema_version": "0.2.0-draft",
                                    "event_id": "evt-001",
                                    "event_name": "product_click",
                                    "intent": "comparison",
                                    "occurred_at": "2026-08-27T14:30:00Z",
                                    "persona_id": null,
                                    "session_id": "session-001",
                                    "page_view_id": "page-view-001",
                                    "sequence_no": 1,
                                    "page_type": "product_list",
                                    "product_id": "product-001",
                                    "actor_type": "user",
                                    "environment": "local",
                                    "properties": {}
                                  }]
                                }
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("KAFKA_UNAVAILABLE"));
    }

    @Test
    void returnsTooManyRequestsWhenThePublisherIsOverloaded() throws Exception {
        when(publisher.publish(anyString(), anyList())).thenReturn(CompletableFuture.failedFuture(
                new EventPublishOverloadedException("publisher overloaded", new RuntimeException("executor saturated"))
        ));

        MvcResult asyncResult = mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(validEventBatch()))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(asyncResult))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().string("Retry-After", "1"))
                .andExpect(jsonPath("$.code").value("INGESTION_OVERLOADED"));
    }

    @Test
    void rejectsMalformedJsonBeforeCallingThePublisher() throws Exception {
        mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{not-valid-json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MALFORMED_JSON"));

        verifyNoInteractions(publisher);
        verify(metrics).recordValidationRejected("malformed_json");
    }

    private String validEventBatch() {
        return """
                {
                  "schema_version": "0.2.0-draft",
                  "events": [{
                    "schema_version": "0.2.0-draft",
                    "event_id": "evt-001",
                    "event_name": "product_click",
                    "intent": "comparison",
                    "occurred_at": "2026-08-27T14:30:00Z",
                    "persona_id": null,
                    "session_id": "session-001",
                    "page_view_id": "page-view-001",
                    "sequence_no": 1,
                    "page_type": "product_list",
                    "product_id": "product-001",
                    "actor_type": "user",
                    "environment": "local",
                    "properties": {}
                  }]
                }
                """;
    }
}
