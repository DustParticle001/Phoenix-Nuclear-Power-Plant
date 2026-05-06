package com.pwrsim.backend.repository;

import com.pwrsim.backend.model.ReactorState;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * Repository for persisting reactor state snapshots.
 * Used for historical data, transient logging, and playback.
 */
@Repository
public interface ReactorStateRepository extends JpaRepository<ReactorState, Long> {
    
    /**
     * Find the most recent reactor state
     */
    Optional<ReactorState> findFirstByOrderByTimestampDesc();
    
    /**
     * Find all states within a time window (for transient analysis)
     */
    List<ReactorState> findByTimestampBetweenOrderByTimestampAsc(Long startTime, Long endTime);
    
    /**
     * Find states where scram was active
     */
    List<ReactorState> findByScramActiveOrderByTimestampDesc(Boolean scramActive);
}
